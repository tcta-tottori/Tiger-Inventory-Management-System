"""TAM 出荷予定登録画面の自動入力

TAM URL: /tam/IO_01_0120_X_01.do?_Action_=a_searchAction

画面構造 (スクリーンショットより):
- 検索条件: 取引先(680502), 入庫年月(発注時), 製造ライン, 品目CD,
             ステータス, 製品部品区分, 仕向地
- 上部ヘッダー: 出荷NO 列ごとのコンテナ情報 (コンテナNO, 工場出荷日, ETD, ETA, 仕向地)
              + 「コンテナ詳細入力」ボタン
- 下部テーブル: 品目行 (区分, 取引先品番, 品目CD, 品名, 入庫年月, 発注合計,
               出荷合計, 注文番号, 発注, 出荷小計, 発注納期, ステータス)
  各品目行 × 各出荷NO 列に数量入力セルがある
- 各品目行に「入力」ボタン, 「メモ」ボタン
- ページネーション: 「次ページ」ボタン (表示ページ:1/総ページ:7)
"""

from __future__ import annotations

from playwright.sync_api import Page

from config import TAM_SHIPPING_URL, TAM_TORIHIKISAKI


def _navigate_to_shipping_page(page: Page, year_month: str) -> None:
    """出荷予定登録ページに遷移して検索を実行する。"""
    url = f"{TAM_SHIPPING_URL}?_Action_=a_searchAction"
    page.goto(url, wait_until="networkidle")

    # 取引先の設定
    torihikisaki = page.query_selector(
        'select[name*="torihikisaki"], input[name*="torihikisaki"]'
    )
    if torihikisaki:
        tag = torihikisaki.evaluate("el => el.tagName.toLowerCase()")
        if tag == "select":
            torihikisaki.select_option(label=f"{TAM_TORIHIKISAKI}")
        else:
            torihikisaki.fill(TAM_TORIHIKISAKI)

    # 入庫年月(発注時) を設定
    ym_input = page.query_selector(
        'input[name*="nyukoYm"], input[name*="hachuYm"], input[name*="yearMonth"]'
    )
    if ym_input:
        ym_input.fill(year_month)

    # 検索ボタンをクリック
    search_btn = page.query_selector(
        'input[value="検索"], button:has-text("検索")'
    )
    if search_btn:
        search_btn.click()
        page.wait_for_load_state("networkidle")


def _get_shipment_columns(page: Page) -> list[str]:
    """上部ヘッダーから出荷NO 列の一覧を取得する。

    Returns:
        出荷NO のリスト (表示順)。例: ["26T0116", "26T0117", ...]
    """
    shipment_nos = []
    # 出荷NO ヘッダー行を探す
    header_cells = page.query_selector_all(
        'td:has-text("出荷ＮＯ"), th:has-text("出荷NO")'
    )

    # ヘッダー行の隣接セルから出荷NO を取得
    if header_cells:
        row = header_cells[0].evaluate("el => el.parentElement")
        if row:
            cells = page.evaluate(
                """(row) => {
                    const tds = row.querySelectorAll('td, th');
                    return Array.from(tds).map(td => td.innerText.trim());
                }""",
                row,
            )
            # 最初のセル ("出荷ＮＯ" ラベル) 以降が出荷NO
            for cell_text in cells[1:]:
                if cell_text and cell_text[0:2].isdigit():
                    shipment_nos.append(cell_text)

    return shipment_nos


def _get_product_rows(page: Page) -> list[dict]:
    """下部テーブルから品目行の情報を取得する。

    Returns:
        品目辞書のリスト。各辞書に品目CD, 行インデックス等を含む。
    """
    products = []
    # 品目テーブルの行を取得
    rows = page.query_selector_all("table tbody tr")

    for idx, row in enumerate(rows):
        cells = row.query_selector_all("td")
        if len(cells) < 6:
            continue

        # 品目CD は通常 3 列目 (0-indexed: 2)
        product_cd = cells[2].inner_text().strip() if len(cells) > 2 else ""
        product_name = cells[3].inner_text().strip() if len(cells) > 3 else ""

        # 品目CD が存在する行のみ
        if product_cd and "-" in product_cd:
            products.append({
                "品目CD": product_cd,
                "品名": product_name,
                "row_index": idx,
                "row_element": row,
            })

    return products


def _find_quantity_inputs_in_row(row, shipment_count: int) -> list:
    """品目行内の数量入力セル (出荷NO 列ごと) を取得する。"""
    inputs = row.query_selector_all("input[type='text']")
    # 出荷NO 列に対応する input のみ (行末の方に配置されている想定)
    if len(inputs) >= shipment_count:
        return inputs[-shipment_count:]
    return inputs


def _process_single_page(
    page: Page,
    aggregated_data: dict[str, dict[str, int]],
    dry_run: bool,
    result: dict,
) -> None:
    """現在表示中の 1 ページ分を処理する。"""
    shipment_nos = _get_shipment_columns(page)
    if not shipment_nos:
        print("[出荷予定登録] 出荷NO 列が見つかりません。")
        return

    print(f"[出荷予定登録] 出荷NO 列: {shipment_nos}")

    product_rows = _get_product_rows(page)
    if not product_rows:
        print("[出荷予定登録] 品目行が見つかりません。")
        return

    for prod in product_rows:
        product_cd = prod["品目CD"]
        if product_cd not in aggregated_data:
            continue

        quantities = aggregated_data[product_cd]
        row_el = prod["row_element"]
        qty_inputs = _find_quantity_inputs_in_row(row_el, len(shipment_nos))

        for col_idx, shipment_no in enumerate(shipment_nos):
            qty = quantities.get(shipment_no, 0)
            if qty <= 0:
                continue

            if dry_run:
                print(f"  {product_cd} × {shipment_no} = {qty}")
                result["filled"] += 1
                continue

            if col_idx < len(qty_inputs):
                try:
                    qty_inputs[col_idx].fill(str(qty))
                    result["filled"] += 1
                    print(f"  {product_cd} × {shipment_no} = {qty} 入力完了")
                except Exception as e:
                    msg = f"{product_cd} × {shipment_no}: {e}"
                    result["errors"].append(msg)
                    print(f"  [ERROR] {msg}")


def register_shipping(
    page: Page,
    aggregated_data: dict[str, dict[str, int]],
    year_month: str,
    dry_run: bool = False,
) -> dict:
    """出荷予定登録を実行する。

    Args:
        page: ログイン済みの Playwright Page。
        aggregated_data: {品目CD: {出荷NO: 数量}} の集計済みデータ。
        year_month: 入庫年月 (例: "202604")。
        dry_run: True の場合は実際の入力は行わない。

    Returns:
        処理結果サマリ辞書。
    """
    result = {"filled": 0, "pages_processed": 0, "errors": []}

    _navigate_to_shipping_page(page, year_month)

    if dry_run:
        print("[出荷予定登録] --dry-run: 以下のデータを入力予定:")

    # ページネーション対応: 全ページを処理
    while True:
        result["pages_processed"] += 1
        print(f"[出荷予定登録] ページ {result['pages_processed']} を処理中...")

        _process_single_page(page, aggregated_data, dry_run, result)

        # 次ページボタンを探す
        next_btn = page.query_selector(
            'input[value="次ページ"], button:has-text("次ページ"), '
            'a:has-text("次ページ")'
        )
        if not next_btn:
            break

        # 次ページボタンが無効化されている場合
        disabled = next_btn.get_attribute("disabled")
        if disabled:
            break

        if not dry_run:
            next_btn.click()
            page.wait_for_load_state("networkidle")
        else:
            # dry-run では次ページに遷移しない (データ変更なし)
            break

    # 確認ボタンをクリック (全ページ処理後)
    if not dry_run and result["filled"] > 0:
        confirm_btn = page.query_selector(
            'input[value="確認"], button:has-text("確認"), '
            'input[value="登録"], button:has-text("登録")'
        )
        if confirm_btn:
            print("[出荷予定登録] 確認/登録ボタンをクリック...")
            confirm_btn.click()
            page.wait_for_load_state("networkidle")
            print("[出荷予定登録] 登録完了。")
        else:
            print("[出荷予定登録] 警告: 確認/登録ボタンが見つかりません。手動で確認してください。")

    print(f"[出荷予定登録] 処理完了: {result['filled']} セル入力, "
          f"{result['pages_processed']} ページ処理, "
          f"{len(result['errors'])} エラー")

    return result
