"""TAM Web システムへのログイン処理"""

from __future__ import annotations

from playwright.sync_api import Page

from config import TAM_BASE_URL, TAM_USER, TAM_PASSWORD


def login(page: Page, user: str = "", password: str = "") -> bool:
    """TAM にログインする。

    Args:
        page: Playwright の Page オブジェクト。
        user: TAM ユーザーID。省略時は環境変数 TAM_USER を使用。
        password: TAM パスワード。省略時は環境変数 TAM_PASSWORD を使用。

    Returns:
        ログイン成功なら True。
    """
    user = user or TAM_USER
    password = password or TAM_PASSWORD

    if not user or not password:
        raise ValueError(
            "TAM_USER / TAM_PASSWORD が設定されていません。"
            "環境変数または引数で指定してください。"
        )

    # TAM トップページにアクセス → ログインフォームが表示される想定
    page.goto(TAM_BASE_URL, wait_until="networkidle")

    # ログインフォームの検出と入力
    # TAM のログインページ構造は実環境で確認が必要。
    # 一般的な Java Struts アプリのフォーム要素を想定:
    #   - ユーザーID: input[name="userId"] or input[name="j_username"]
    #   - パスワード: input[name="password"] or input[name="j_password"]
    #   - ログインボタン: input[type="submit"] or button

    # 複数の候補セレクタを試行
    user_selectors = [
        'input[name="userId"]',
        'input[name="j_username"]',
        'input[name="username"]',
        'input[name="loginId"]',
        'input[type="text"]',
    ]
    pass_selectors = [
        'input[name="password"]',
        'input[name="j_password"]',
        'input[name="passwd"]',
        'input[type="password"]',
    ]

    user_input = None
    for selector in user_selectors:
        el = page.query_selector(selector)
        if el:
            user_input = el
            break

    pass_input = None
    for selector in pass_selectors:
        el = page.query_selector(selector)
        if el:
            pass_input = el
            break

    if not user_input or not pass_input:
        # ログインフォームが見つからない場合、既にログイン済みの可能性
        if _is_logged_in(page):
            print("[TAM Login] 既にログイン済みです。")
            return True
        raise RuntimeError(
            "TAM ログインフォームが見つかりません。"
            "URL やページ構造を確認してください。"
        )

    user_input.fill(user)
    pass_input.fill(password)

    # ログインボタンをクリック
    submit_selectors = [
        'input[type="submit"]',
        'button[type="submit"]',
        'input[value="ログイン"]',
        'button:has-text("ログイン")',
    ]
    for selector in submit_selectors:
        btn = page.query_selector(selector)
        if btn:
            btn.click()
            break
    else:
        # submit ボタンが見つからなければ Enter キーで送信
        pass_input.press("Enter")

    page.wait_for_load_state("networkidle")

    if _is_logged_in(page):
        print("[TAM Login] ログイン成功。")
        return True

    raise RuntimeError("TAM ログインに失敗しました。ユーザーID/パスワードを確認してください。")


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
