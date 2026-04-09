"""Google Sheets からコンテナ登録/出荷予定明細データを読み取る"""

from __future__ import annotations

import gspread
from google.oauth2.service_account import Credentials

from config import (
    CREDENTIALS_PATH,
    SPREADSHEET_ID,
    SHEET_CONTAINER,
    SHEET_SHIPPING,
    CONTAINER_SHEET_COLS,
    CONTAINER_DATA_START,
    SHIPPING_SHEET_COLS,
    SHIPPING_DATA_START,
    PORT_MAP,
)


def _get_client() -> gspread.Client:
    """Google Sheets API クライアントを取得する。"""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
    return gspread.authorize(creds)


def _normalize_date(value: str) -> str:
    """日付文字列を YYYY/MM/DD 形式に正規化する。

    Google Sheets から取得される日付は複数の形式がありうる:
    - "2026/01/28"
    - "2026/1/28"
    - "1/28/2026"  (ロケール依存)
    可能な限り YYYY/MM/DD に変換する。
    """
    if not value or not isinstance(value, str):
        return str(value) if value else ""

    value = value.strip()

    # 既に YYYY/MM/DD or YYYY-MM-DD 形式
    for sep in ("/", "-"):
        parts = value.split(sep)
        if len(parts) == 3:
            if len(parts[0]) == 4:  # YYYY/MM/DD
                y, m, d = parts
                return f"{y}/{int(m):02d}/{int(d):02d}"
            if len(parts[2]) == 4:  # MM/DD/YYYY
                m, d, y = parts
                return f"{y}/{int(m):02d}/{int(d):02d}"
    return value


def _normalize_port(value: str) -> str:
    """仕向地を TAM 形式 (東京/大阪) に変換する。"""
    return PORT_MAP.get(str(value).strip(), str(value).strip())


def get_container_data(month_period: str) -> list[dict]:
    """コンテナ登録シートから指定月期のデータを取得する。

    Args:
        month_period: 月期文字列。シート側の月期フィルタに使う。
            例: "3月期" or "202603" — シートのフィルタ方式に依存。
            空文字列の場合は全件取得。

    Returns:
        各コンテナのデータ辞書のリスト。
    """
    client = _get_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_CONTAINER)
    all_rows = ws.get_all_values()

    # データ開始行以降を取得 (0-indexed に変換)
    data_rows = all_rows[CONTAINER_DATA_START - 1:]

    cols = CONTAINER_SHEET_COLS
    results = []
    for row in data_rows:
        if len(row) <= cols["出荷NO"]:
            continue
        shipment_no = str(row[cols["出荷NO"]]).strip()
        if not shipment_no:
            continue

        record = {
            "出荷NO": shipment_no,
            "コンテナNO": str(row[cols["コンテナNO"]]).strip() if len(row) > cols["コンテナNO"] else "",
            "工場出荷日": _normalize_date(row[cols["工場出荷日"]]) if len(row) > cols["工場出荷日"] else "",
            "ETD": _normalize_date(row[cols["ETD"]]) if len(row) > cols["ETD"] else "",
            "ETA": _normalize_date(row[cols["ETA"]]) if len(row) > cols["ETA"] else "",
            "仕向地": _normalize_port(row[cols["仕向地"]]) if len(row) > cols["仕向地"] else "",
            "本船名": str(row[cols["本船名"]]).strip() if len(row) > cols["本船名"] else "",
        }
        results.append(record)

    return results


def get_shipping_data(year_month: str) -> list[dict]:
    """出荷予定明細シートから指定年月のデータを取得する。

    Args:
        year_month: 年月文字列 (例: "202604")。
            出荷NO の先頭プレフィクスでフィルタする。
            例: "202604" → "26T04" → REF No. が "26T04xx" のもの。

    Returns:
        品目CD × 出荷NO ごとの数量データ辞書のリスト。
    """
    client = _get_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_SHIPPING)
    all_rows = ws.get_all_values()

    data_rows = all_rows[SHIPPING_DATA_START - 1:]

    cols = SHIPPING_SHEET_COLS
    results = []
    for row in data_rows:
        if len(row) <= cols["出荷NO"]:
            continue
        shipment_no = str(row[cols["出荷NO"]]).strip()
        if not shipment_no:
            continue

        record = {
            "出荷NO": shipment_no,
            "工場出荷日": _normalize_date(row[cols["工場出荷日"]]) if len(row) > cols["工場出荷日"] else "",
            "品目CD": str(row[cols["品目CD"]]).strip() if len(row) > cols["品目CD"] else "",
            "数量": row[cols["数量"]] if len(row) > cols["数量"] else "",
            "月期": str(row[cols["月期"]]).strip() if len(row) > cols["月期"] else "",
            "ETD": _normalize_date(row[cols["ETD"]]) if len(row) > cols["ETD"] else "",
            "ETA": _normalize_date(row[cols["ETA"]]) if len(row) > cols["ETA"] else "",
            "仕向地": _normalize_port(row[cols["仕向地"]]) if len(row) > cols["仕向地"] else "",
        }
        results.append(record)

    # year_month でフィルタ: "202604" → prefix "26T04"
    if year_month and len(year_month) == 6:
        prefix = year_month[2:4] + "T" + year_month[4:6]
        results = [r for r in results if r["出荷NO"].startswith(prefix)]

    return results


def aggregate_shipping_by_product(shipping_data: list[dict]) -> dict[str, dict[str, int]]:
    """出荷データを 品目CD → {出荷NO: 数量} に集計する。

    Returns:
        {品目CD: {出荷NO: 合計数量}} の辞書。
    """
    aggregated: dict[str, dict[str, int]] = {}
    for row in shipping_data:
        product = row["品目CD"]
        shipment = row["出荷NO"]
        if not product or not shipment:
            continue
        try:
            qty = int(str(row["数量"]).replace(",", ""))
        except (ValueError, TypeError):
            qty = 0
        if product not in aggregated:
            aggregated[product] = {}
        aggregated[product][shipment] = aggregated[product].get(shipment, 0) + qty
    return aggregated
