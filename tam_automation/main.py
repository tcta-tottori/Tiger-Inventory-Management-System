#!/usr/bin/env python3
"""TAM 自動入力システム — CLI エントリポイント

使用例:
    # コンテナ登録
    python main.py container --month 202603

    # 出荷予定登録
    python main.py shipping --month 202604

    # 両方実行
    python main.py both --month 202604

    # 確認のみ (実際の登録は行わない)
    python main.py container --month 202603 --dry-run

    # ヘッドレスモード (ブラウザ非表示)
    python main.py container --month 202603 --headless
"""

from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright

from config import TAM_USER, TAM_PASSWORD, SPREADSHEET_ID
from tam_login import login
from sheets_reader import get_container_data, get_shipping_data, aggregate_shipping_by_product
from container_registration import register_containers
from shipping_registration import register_shipping


def _validate_config() -> list[str]:
    """設定の妥当性を検証する。"""
    errors = []
    if not TAM_USER:
        errors.append("環境変数 TAM_USER が設定されていません。")
    if not TAM_PASSWORD:
        errors.append("環境変数 TAM_PASSWORD が設定されていません。")
    if not SPREADSHEET_ID:
        errors.append("環境変数 SPREADSHEET_ID が設定されていません。")
    return errors


def _run_container(page, args) -> dict:
    """コンテナ登録を実行する。"""
    print("=" * 60)
    print(f"コンテナ登録 — 入庫年月: {args.month}")
    print("=" * 60)

    print("[1/2] Google Sheets からコンテナデータを取得中...")
    containers = get_container_data(args.month)
    print(f"  取得件数: {len(containers)} 件")

    if not containers:
        print("  登録対象のコンテナデータがありません。")
        return {"added": 0, "skipped": 0, "errors": []}

    print("[2/2] TAM コンテナ登録を実行中...")
    result = register_containers(page, containers, args.month, dry_run=args.dry_run)

    return result


def _run_shipping(page, args) -> dict:
    """出荷予定登録を実行する。"""
    print("=" * 60)
    print(f"出荷予定登録 — 入庫年月: {args.month}")
    print("=" * 60)

    print("[1/2] Google Sheets から出荷予定データを取得中...")
    shipping_data = get_shipping_data(args.month)
    print(f"  取得件数: {len(shipping_data)} 件")

    if not shipping_data:
        print("  登録対象の出荷予定データがありません。")
        return {"filled": 0, "pages_processed": 0, "errors": []}

    aggregated = aggregate_shipping_by_product(shipping_data)
    print(f"  品目数: {len(aggregated)}")
    total_cells = sum(len(v) for v in aggregated.values())
    print(f"  入力予定セル数: {total_cells}")

    print("[2/2] TAM 出荷予定登録を実行中...")
    result = register_shipping(page, aggregated, args.month, dry_run=args.dry_run)

    return result


def _print_summary(mode: str, results: list[dict]) -> None:
    """処理結果のサマリを表示する。"""
    print("\n" + "=" * 60)
    print("処理結果サマリ")
    print("=" * 60)

    for r in results:
        if "added" in r:
            print(f"[コンテナ登録] 追加: {r['added']}件, スキップ: {r['skipped']}件, "
                  f"エラー: {len(r['errors'])}件")
        if "filled" in r:
            print(f"[出荷予定登録] 入力: {r['filled']}セル, "
                  f"ページ: {r['pages_processed']}, "
                  f"エラー: {len(r['errors'])}件")

        if r.get("errors"):
            print("  エラー詳細:")
            for err in r["errors"]:
                print(f"    - {err}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="TAM 自動入力システム — Google Sheets → TAM Web",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "mode",
        choices=["container", "shipping", "both"],
        help="実行モード: container=コンテナ登録, shipping=出荷予定登録, both=両方",
    )
    parser.add_argument(
        "--month",
        required=True,
        help="入庫年月 (例: 202604)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="確認のみ (実際の登録は行わない)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="ヘッドレスモード (ブラウザ非表示)",
    )

    args = parser.parse_args()

    # 設定検証
    config_errors = _validate_config()
    if config_errors:
        print("設定エラー:")
        for err in config_errors:
            print(f"  - {err}")
        print("\n必要な環境変数を設定してください:")
        print("  export TAM_USER='your_user_id'")
        print("  export TAM_PASSWORD='your_password'")
        print("  export SPREADSHEET_ID='your_spreadsheet_id'")
        return 1

    if args.dry_run:
        print("*** DRY-RUN モード: 実際の登録は行いません ***\n")

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="ja-JP",
        )
        page = context.new_page()

        try:
            # TAM ログイン
            print("[TAM Login] ログイン中...")
            login(page)

            # 指定モードの実行
            if args.mode in ("container", "both"):
                result = _run_container(page, args)
                results.append(result)

            if args.mode in ("shipping", "both"):
                result = _run_shipping(page, args)
                results.append(result)

            _print_summary(args.mode, results)

        except Exception as e:
            print(f"\n[ERROR] 予期しないエラー: {e}")
            # エラー時のスクリーンショットを保存
            page.screenshot(path="tam_error_screenshot.png")
            print("  エラー時のスクリーンショットを tam_error_screenshot.png に保存しました。")
            return 1

        finally:
            browser.close()

    # エラーがあれば終了コード 1
    has_errors = any(r.get("errors") for r in results)
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
