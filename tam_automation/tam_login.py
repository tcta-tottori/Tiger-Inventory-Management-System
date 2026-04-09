"""TAM Web システムへの手動ログイン待機処理"""

from __future__ import annotations

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from config import TAM_BASE_URL


def manual_login(page: Page, timeout: int = 300) -> bool:
    """ブラウザで TAM を開き、ユーザーの手動ログインを待機する。

    Args:
        page: Playwright の Page オブジェクト。
        timeout: ログイン待機のタイムアウト秒数 (デフォルト 300秒)。

    Returns:
        ログイン確認できたら True。
    """
    # TAM トップページにアクセス
    page.goto(TAM_BASE_URL, wait_until="networkidle")

    # 既にログイン済みならスキップ
    if _is_logged_in(page):
        print("[TAM Login] 既にログイン済みです。")
        return True

    print("[TAM Login] ブラウザが開きました。TAM にログインしてください。")
    print(f"[TAM Login] ログイン完了まで待機中... (タイムアウト: {timeout}秒)")

    try:
        page.wait_for_selector(
            'a:has-text("ログアウト")',
            timeout=timeout * 1000,
        )
    except PlaywrightTimeout:
        raise RuntimeError(
            f"TAM ログインがタイムアウトしました ({timeout}秒)。"
            "ブラウザでログインを完了してからやり直してください。"
        )

    if not _is_logged_in(page):
        raise RuntimeError("TAM ログインの確認に失敗しました。")

    print("[TAM Login] ログイン確認完了。自動化を開始します。")
    return True


def _is_logged_in(page: Page) -> bool:
    """現在のページがログイン後の状態かどうかを判定する。

    TAM メニューページの特徴:
    - "ログアウト" リンクが存在する
    - URL に "_link.do" を含む (メニュー) または機能ページ
    """
    # ログアウトリンクの存在で判定
    logout = page.query_selector('a:has-text("ログアウト")')
    if logout:
        return True

    # URL パターンで判定
    url = page.url
    if "_link.do" in url or "IO_01" in url:
        return True

    return False
