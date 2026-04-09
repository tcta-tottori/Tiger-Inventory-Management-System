# Tiger Inventory Management System

Google Sheets + Google Apps Script (GAS) による在庫・出荷管理自動化システム、
および TAM (Tiger Arrival Management) Web システムへの自動入力ツール。

気高電機（新建高）向けの出荷予定明細管理、コンテナ登録、入荷予定表生成、
INVOICE 処理を自動化する。

---

## リポジトリ構成

| ファイル | 種別 | 役割 |
|---|---|---|
| `MAIN.txt` | GAS | メイン: メニュー作成、REF No. 更新、入荷予定表生成、コンテナ管理 |
| `Adjust.txt` | GAS | 数量自動調整: 月期別差異解消、行分割・月期振替、バックアップ |
| `invoice.txt` | GAS | INVOICE 統合: 出荷明細インポート/出力、アフター部品リスト生成 |
| `タイガー関係 Ver.2.xlsx` | Excel | メインスプレッドシート (GAS の実行対象) |
| `インストン.xlsx` | Excel | コンテナ No. マスタ (REF No. → コンテナ No. マッピング) |
| `INVOICE自動処理システム_Ver.1.3.xlsm` | Excel | INVOICE 用補助ブック (読込、出荷明細用、注残リスト) |
| `タイガー様入荷予定(新建高).xls` | Excel | 新建高別入荷予定テンプレート |
| `タイガーハンカン3.xlsm` | Excel | 反韓処理用ブック |
| `タイガー注残リスト.xlsm` | Excel | 注残情報マスタ |
| `コンテナメール送付.xlsm` | Excel | メール送付ユーティリティ |
| `tam_automation/` | Python | TAM Web システム自動入力ツール |

---

## カスタムメニュー リファレンス

Google Sheets を開くと以下のメニューが自動追加される (`MAIN.txt` の `onOpen` 関数)。

```
▼メニュー
├─ プルダウン更新         コンテナ登録 B2 のドロップダウンを月期から動的生成
├─ REF No.更新            月度シートに REF No. を工場出荷日順でソート挿入
├─ アフター部品更新       注残リスト参照でアフター部品情報を更新
└─ 数量自動調整           開始月期指定 → 東京/大阪向け数量差異を自動調整 (バックアップ付き)

▼INVOICE
├─ ▼出荷明細用インポート  「読込」→「出荷明細用」シートへデータインポート
├─ ▼出荷予定明細出力      「出荷明細用」→「出荷予定明細」シートへ REF No. 昇順で出力
├─ ▽アフター部品出力      チェック行 → 注残リスト参照 → アフター部品リスト生成・ダウンロード
└─ ▽データクリア（出荷明細用）  出荷明細用シートのデータをクリア
```

---

## 主要機能の詳細

### REF No. 更新
- **対象**: 月度シート (「月度」を含むシート名)
- **処理**: コンテナ登録シートの REF No. を工場出荷日でソートし I1 行に挿入
- **GAS 関数**: `updateRefNo()` (`MAIN.txt`)

### プルダウン更新 (コンテナ登録)
- **対象**: コンテナ登録シート B2
- **処理**: J 列の月期データからドロップダウンを動的生成
- **GAS 関数**: `createContainerDropdown()` (`MAIN.txt`)

### 入荷予定表生成
- **入力**: 入荷予定書込シートの B2 (出荷番号)・B4 (月期)
- **処理**: 出荷予定明細から月期でフィルタ → 品目CD ごとに集約 → 入荷予定シートに出力 → Excel エクスポート
- **GAS 関数**: `createArrivalSchedule()` (`MAIN.txt`)

### 数量自動調整
- **入力**: 開始月期 (UI プロンプト)
- **処理**: バックアップ作成 → 東京向け/大阪向けの順に差異を検出 → 出荷予定明細内で月期間の行分割・振替
- **GAS 関数**: `adjustQuantities()` → `runAdjustProcess()` (`Adjust.txt`)

### INVOICE パイプライン
3段階処理: 読込 → 出荷明細用 → 出荷予定明細
- **インポート**: `importFromYomikomiSheet()` (`invoice.txt`)
- **出力**: `exportShukkaYoToShippingScheduleMenu()` (`invoice.txt`)
- **アフター部品**: `exportAfterPartsList()` (`invoice.txt`)

---

## 参照シート一覧

GAS 内にハードコードされているシート名。**シート名を変更すると GAS が動作しなくなる。**

| シート名 | 用途 |
|---|---|
| 出荷予定明細 | ソースデータ (REF No., 品目CD, 数量, 月期, ETD, ETA, 仕向地) |
| 入荷予定書込 | 入荷予定生成の入力パラメータ (出荷番号, 月期) |
| 入荷予定 | 入荷予定生成の出力先 |
| コード | 品目コード → 品名/区分のマスタ |
| 確定分 | 確定済み REF No. の一覧 |
| コンテナ登録 | コンテナ情報管理 (出荷NO, コンテナNO, ETD, ETA, 仕向地, 本船名) |
| 東京向け | 東京向け出荷数量 (数量調整の参照先) |
| 大阪向け | 大阪向け出荷数量 (数量調整の参照先) |
| 読込 | INVOICE インポート元 |
| 出荷明細用 | INVOICE 中間処理シート |
| 注残リスト | アフター部品の参照マスタ |
| アフター部品リスト | アフター部品出力先 |
| 設定 | 項目名-値ペアの設定シート |

---

## TAM 自動入力システム

### 概要

TAM (Tiger Arrival Management / https://tam.toraud.com ) への手作業入力を自動化する
Python + Playwright ベースのブラウザ自動化ツール。

Google Sheets のデータを読み取り、TAM の以下の画面に自動入力する:

- **コンテナ登録** — コンテナ登録シート → TAM コンテナ登録画面
- **出荷予定登録** — 出荷予定明細シート → TAM 出荷予定登録画面

### セットアップ

```bash
# 1. Python 仮想環境の作成
cd tam_automation
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. 依存パッケージのインストール
pip install -r requirements.txt

# 3. Playwright ブラウザのインストール
playwright install chromium

# 4. Google Sheets API 認証の設定
#    Google Cloud Console でサービスアカウントを作成し、
#    JSON キーファイルを credentials/service_account.json に配置
#    対象スプレッドシートをサービスアカウントに共有する

# 5. 環境変数の設定
export SPREADSHEET_ID='your_google_spreadsheet_id'
```

### 使い方

```bash
cd tam_automation

# コンテナ登録
python main.py container --month 202603

# 出荷予定登録
python main.py shipping --month 202604

# 両方実行
python main.py both --month 202604

# 確認のみ (実際の登録は行わない)
python main.py container --month 202603 --dry-run
```

> **注意:** 実行するとブラウザが開きます。TAM のログイン画面が表示されたら手動でログインしてください。ログイン完了を検知すると自動処理が開始されます。

### データフロー

```
Google Sheets (タイガー関係 Ver.2)
    │
    ├─ コンテナ登録シート ──→ TAM コンテナ登録画面
    │   (出荷NO, コンテナNO,     (出荷NO, コンテナNO,
    │    工場出荷日, ETD, ETA,    工場出荷日, ETD, ETA,
    │    仕向地, 本船名)          仕向地, 本船名, サイズ)
    │
    └─ 出荷予定明細シート ──→ TAM 出荷予定登録画面
        (出荷NO, 品目CD,         (品目CD × 出荷NO 列に
         数量, 月期)              数量を入力)
```

---

## GAS セットアップ手順

1. `タイガー関係 Ver.2.xlsx` を Google Sheets にアップロード (Google 形式に変換)
2. 拡張機能 → Apps Script を開く
3. 以下の `.txt` ファイルの内容を `.gs` ファイルとして貼り付ける:
   - `MAIN.txt` → `MAIN.gs`
   - `Adjust.txt` → `Adjust.gs`
   - `invoice.txt` → `invoice.gs`
4. 保存 → スプレッドシートを再読み込み
5. `▼メニュー` / `▼INVOICE` メニューが表示されることを確認
6. 初回実行時に権限承認ダイアログが出るので許可

---

## 運用上の注意

- **数量自動調整**: 実行前に自動でシートをバックアップする (`createSheetBackup_`)。
  念のため手動バックアップも推奨。
- **シート名の変更/削除**: GAS のハードコード参照を壊すため禁止。
- **インストン.xlsx**: REF → コンテナ No. マッピングに使用。
  同一スプレッドシートに別シートとして取り込む必要がある。
- **バージョン管理**: 本リポジトリは GAS コードを `.txt` 形式で保管。
  正本は Google Sheets 側の Apps Script エディタ。
  Excel テンプレートはバイナリ差分が見えないため、変更時はコミットメッセージに変更内容を明記すること。
