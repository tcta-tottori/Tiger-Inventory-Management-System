"""TAM コンテナ登録画面の自動入力

TAM URL: /tam/IO_01_0200_IO_01.do?_Action_=a_searchAction

画面構造 (スクリーンショットより):
- 検索条件: 取引先, 入庫年月(発注時), 製造ライン, 仕向地
- 一覧: 出荷NO, コンテナNO, 工場出荷日, ETD, ETA, 仕向地(dropdown),
         本船名, 音積, サイズ(dropdown)
- 操作: +/- ボタンで行追加/削除, 「登録」ボタンで確定
"""

from __future__ import annotations

from playwright.sync_api import Page

from config import TAM_CONTAINER_URL, TAM_TORIHIKISAKI, TAM_DEFAULT_SIZE


def _navigate_to_container_page(page: Page, year_month: str) -> None:
    """コンテナ登録ページに遷移して検索を実行する。"""
    url = f"{TAM_CONTAINER_URL}?_Action_=a_searchAction"
    page.goto(url, wait_until="networkidle")

    # 取引先が既にセットされているか確認 (通常ログインユーザーに紐付き)
    torihikisaki = page.query_selector('select[name*="torihikisaki"], input[name*="torihikisaki"]')
    if torihikisaki:
        tag = torihikisaki.evaluate("el => el.tagName.toLowerCase()")
        if tag == "select":
            torihikisaki.select_option(label=f"{TAM_TORIHIKISAKI}")
        else:
            torihikisaki.fill(TAM_TORIHIKISAKI)

    # 入庫年月(発注時) を設定
    year_month_input = page.query_selector(
        'input[name*="nyukoYm"], input[name*="hachuYm"], input[name*="yearMonth"]'
    )
    if year_month_input:
        year_month_input.fill(year_month)

    # 検索ボタンをクリック
    search_btn = page.query_selector(
        'input[value="検索"], button:has-text("検索")'
    )
    if search_btn:
        search_btn.click()
        page.wait_for_load_state("networkidle")


def _get_existing_shipment_nos(page: Page) -> set[str]:
    """現在 TAM に表示されている出荷NO の一覧を取得する。"""
    existing = set()
    # 出荷NO 列のセルを取得 (input フィールド)
    inputs = page.query_selector_all(
        'input[name*="shukkaNo"], input[name*="shipNo"], '
        'td input[name*="shukka"]'
    )
    for inp in inputs:
        val = inp.input_value().strip()
        if val:
            existing.add(val)

    # input ではなくテキスト表示の場合もある
    if not existing:
        rows = page.query_selector_all("table tbody tr")
        for row in rows:
            cells = row.query_selector_all("td")
            if len(cells) >= 2:
                text = cells[1].inner_text().strip()
                if text and text[0:2].isdigit():
                    existing.add(text)

    return existing


def _add_new_row(page: Page) -> None:
    """新規行追加ボタン (+) をクリックする。"""
    add_btn = page.query_selector(
        'input[value="+"], button:has-text("+"), '
        'a:has-text("+"), img[alt="追加"]'
    )
    if add_btn:
        add_btn.click()
        page.wait_for_timeout(500)


def _fill_container_row(
    page: Page,
    row_index: int,
    data: dict,
) -> None:
    """コンテナ登録テーブルの指定行にデータを入力する。

    Args:
        page: Playwright Page。
        row_index: テーブル内の行インデックス (0-based)。
        data: コンテナデータ辞書。
    """
    # TAM のフォーム名パターン: name="list[{index}].fieldName"
    # Java Struts ではよくある配列形式
    prefix = f"list[{row_index}]"

    field_map = {
        "shukkaNo": data["出荷NO"],
        "containerNo": data["コンテナNO"],
    }

    # テキストフィールドの入力
    for field_name, value in field_map.items():
        selector = f'input[name="{prefix}.{field_name}"]'
        el = page.query_selector(selector)
        if not el:
            # name 属性が異なる場合、行の input を順番で探す
            el = _find_input_in_row(page, row_index, field_name)
        if el:
            el.fill(str(value))

    # 日付フィールド (date picker): 直接 input に値を入力
    date_fields = {
        "factoryShipDate": data["工場出荷日"],
        "etd": data["ETD"],
        "eta": data["ETA"],
    }
    for field_name, value in date_fields.items():
        selector = f'input[name="{prefix}.{field_name}"]'
        el = page.query_selector(selector)
        if not el:
            el = _find_input_in_row(page, row_index, field_name)
        if el and value:
            el.fill(str(value))

    # 仕向地ドロップダウン
    port_selector = f'select[name="{prefix}.shimukechi"], select[name="{prefix}.port"]'
    port_el = page.query_selector(port_selector)
    if port_el:
        port_el.select_option(label=data["仕向地"])
    else:
        port_el = _find_select_in_row(page, row_index, 0)
        if port_el:
            port_el.select_option(label=data["仕向地"])

    # 本船名
    vessel_selector = f'input[name="{prefix}.vesselName"], input[name="{prefix}.honsenMei"]'
    vessel_el = page.query_selector(vessel_selector)
    if not vessel_el:
        vessel_el = _find_input_in_row(page, row_index, "vessel")
    if vessel_el and data["本船名"]:
        vessel_el.fill(data["本船名"])

    # サイズドロップダウン
    size_selector = f'select[name="{prefix}.size"]'
    size_el = page.query_selector(size_selector)
    if not size_el:
        size_el = _find_select_in_row(page, row_index, 1)
    if size_el:
        size_el.select_option(value=TAM_DEFAULT_SIZE)


def _find_input_in_row(page: Page, row_index: int, hint: str):
    """テーブルの指定行から hint に近い input 要素を探す。"""
    rows = page.query_selector_all("table tbody tr")
    if row_index < len(rows):
        inputs = rows[row_index].query_selector_all("input[type='text']")
        for inp in inputs:
            name = inp.get_attribute("name") or ""
            if hint.lower() in name.lower():
                return inp
    return None


def _find_select_in_row(page: Page, row_index: int, select_index: int):
    """テーブルの指定行から N 番目の select 要素を返す。"""
    rows = page.query_selector_all("table tbody tr")
    if row_index < len(rows):
        selects = rows[row_index].query_selector_all("select")
        if select_index < len(selects):
            return selects[select_index]
    return None


def register_containers(
    page: Page,
    containers: list[dict],
    year_month: str,
    dry_run: bool = False,
) -> dict:
    """コンテナ登録を実行する。

    Args:
        page: ログイン済みの Playwright Page。
        containers: Google Sheets から取得したコンテナデータリスト。
        year_month: 入庫年月 (例: "202603")。
        dry_run: True の場合は実際の登録は行わない。

    Returns:
        処理結果サマリ辞書。
    """
    result = {"added": 0, "skipped": 0, "errors": []}

    _navigate_to_container_page(page, year_month)

    existing = _get_existing_shipment_nos(page)
    print(f"[コンテナ登録] TAM 既存データ: {len(existing)} 件")

    new_containers = [c for c in containers if c["出荷NO"] not in existing]
    skip_count = len(containers) - len(new_containers)
    result["skipped"] = skip_count

    if skip_count > 0:
        print(f"[コンテナ登録] スキップ (既存): {skip_count} 件")

    if not new_containers:
        print("[コンテナ登録] 新規登録対象なし。")
        return result

    print(f"[コンテナ登録] 新規登録対象: {len(new_containers)} 件")

    if dry_run:
        print("[コンテナ登録] --dry-run: 以下のデータを登録予定:")
        for c in new_containers:
            print(f"  {c['出荷NO']}  {c['コンテナNO']}  {c['工場出荷日']}  "
                  f"ETD:{c['ETD']}  ETA:{c['ETA']}  {c['仕向地']}  {c['本船名']}")
        result["added"] = len(new_containers)
        return result

    # 既存行数を取得 (新規行の開始インデックス)
    current_row_count = len(existing)

    for i, container in enumerate(new_containers):
        try:
            _add_new_row(page)
            row_idx = current_row_count + i
            _fill_container_row(page, row_idx, container)
            result["added"] += 1
            print(f"  [{i + 1}/{len(new_containers)}] {container['出荷NO']} 入力完了")
        except Exception as e:
            msg = f"{container['出荷NO']}: {e}"
            result["errors"].append(msg)
            print(f"  [ERROR] {msg}")

    # 登録ボタンをクリック
    submit_btn = page.query_selector(
        'input[value="登録"], button:has-text("登録")'
    )
    if submit_btn:
        print("[コンテナ登録] 登録ボタンをクリック...")
        submit_btn.click()
        page.wait_for_load_state("networkidle")
        print("[コンテナ登録] 登録完了。")
    else:
        print("[コンテナ登録] 警告: 登録ボタンが見つかりません。手動で確認してください。")

    return result
