# DLサンプル(コラム記事のダウンロード資料)制作工程

コラム記事に埋め込む `<aside class="dl-card">` から配布する、xlsxサンプル資料の制作手順。SEOコラム本編のパイプライン(`pipeline-v3.md`)とは別系統の工程で、このファイルが正本。

## 全体像

- 実体は `scripts/downloads-gen/` にある。記事1本につき生成スクリプト `gen_<slug相当>_sample.py` を1本用意し、実行すると `public/downloads/<資料名>-sample.xlsx` を上書き生成する
- 生成物の `public/downloads/*.xlsx` はリポジトリに直接コミットする資産。`public/images/` と違い、prebuild同期の対象ではない(gitignore対象外)
- 記事本文への組み込みは、生成したxlsxとは別に次の2点が必要
  - `content/column/<slug>.md` 内の `<aside class="dl-card">` ブロック(DLボタン・説明文・AI相談導線)
  - `content/images/column/<slug>/dl-preview-*.webp`(サンプル1ページ目のプレビュー画像、`gen_dl_preview.py` が生成)
- 制作タイミングはコラム本編の執筆・公開作業とは独立。既存の公開済み記事に後追いで追加することも、新規記事の執筆時にあわせて追加することもある(過去バッチはいずれも既存記事への後追い)

## 新規サンプル追加の手順

### 1. gen_*.py の書き方

- ファイル名は `scripts/downloads-gen/gen_<資料名>_sample.py`
- 既存の `_common.py` を使うスクリプト(例: `gen_ai_content_workflow_sample.py`)を土台にコピーして書く。パイロット5本の一部(`gen_ai_task_audit_sample.py` など)は `_common.py` 導入前の実装で、docProps・印刷設定をスクリプト内に直接持っている旧方式が残っているが、新規に書くスクリプトは `_common.py` を使う
- 冒頭で次を import する
  ```python
  sys.path.insert(0, str(Path(__file__).parent))
  from _common import apply_std_setup, fix_docprops_modified
  ```
- `build_workbook()` でシート内容を組み立て、最後に `apply_std_setup(wb, title)` を呼んで印刷設定・freeze pane選択・docPropsをまとめて適用する
- `main()` で `public/downloads/` に保存したあと、必ず `fix_docprops_modified(out_path)` を呼ぶ。openpyxlは保存時に `dcterms:modified` を実行時刻で上書きするため、これを呼ばないと `created` より過去になる逆転が起きる
- 記入例の題材は架空の企業・人物にする。実在のクライアント名は書かない(コラム全体の表記ルールと同じ)
- 数値の記入例は「短時間」「半日程度を見込む想定」のような相対表現にとどめ、出典のない具体数値を書かない

### 2. DL_SAMPLE_DATE の指定と実行

`_common.py` は環境変数 `DL_SAMPLE_DATE=YYYY-MM-DD` を必須にしている。未指定だと `SystemExit` になる。

```bash
DL_SAMPLE_DATE=2026-08-15 python3 scripts/downloads-gen/gen_<資料名>_sample.py
```

- この日付は生成xlsxのdocProps(`created` / `modified`)とzipエントリの格納時刻に使われる
- 新規サンプルを作る日は、その日の日付を指定する
- 既存サンプルを同じ内容で再生成する場合(依存ライブラリ更新後の再ビルド等)は、当時のバッチで使った日付を指定するとバイト一致の再現生成になる。過去バッチで使われた日付は `docProps/core.xml` の `created` から確認できる

### 3. 生成物の置き場所

- xlsx本体: `public/downloads/<資料名>-sample.xlsx`(コミット対象)
- プレビュー画像: `content/images/column/<slug>/dl-preview-<MD5先頭8桁>.webp`

### 4. プレビュー画像の生成

`gen_dl_preview.py` が xlsx を LibreOffice + poppler でPDF化し、1ページ目上部を切り出してwebpにする。

```bash
python3 scripts/downloads-gen/gen_dl_preview.py <slug> --alt "<alt文>"
```

- 前提として記事mdに `dl-card` とDLボタン(`href="/downloads/*.xlsx"`)が先に入っている必要がある
- 依存: `soffice`(LibreOffice)、`pdftoppm`(poppler)、Pillow
- 既存のプレビューを同じaltで再生成する場合は `--alt` を省略できる(既存ブロックのaltを引き継ぐ)
- 生成のたびにファイル名のハッシュが変わり、記事md内の参照とimmutableキャッシュの整合を保つ。md更新が成功したあとに旧ハッシュのwebpを削除する

### 5. 記事への組み込み(dl-card)

`dl-card` の追加方法は、コラム本文のHTML断片が単一ソース化される見込み(並行して進行中)のため、本書では個別のHTML手順を正としない。単一ソース化後の生成方式に従って追加する。単一ソース化前の暫定運用としては、既存記事(例: `content/column/ai-ad-creative-guide.md`)の `dl-card` ブロックを参照し、DLボタンのhref・`data-cta-item`・AI相談導線のクエリ文言を対象記事に合わせて書き換える。

## 品質ゲート

xlsxを作成・更新したら、納品(コミット)前に必ず品質ゲートを実行する。

```bash
python3 ~/.claude/skills/xlsx/xlsx_quality_gate.py public/downloads/<資料名>-sample.xlsx --render-pdf
```

- パスはリポジトリ外(`~/.claude/skills/xlsx/`)にあるユーザー環境のスキルディレクトリ。リポジトリ内には存在しない
- 確認項目: ZIP整合性、XMLパース、openpyxl読み込み、非表示行列、freeze pane選択の不整合、折り返しテキストの行高不足、Excelエラー文字列、LibreOffice/PDFレンダリング
- 指摘があれば `--fix --out <fixed>.xlsx` で自動修復し、再度ゲートを通す

## 過去バッチの経緯

| バッチ | 内容 | 対象記事数 | 主なPR |
|---|---|---|---|
| 記事設計シート(起点) | `seo-article-design-sheet-sample.xlsx` を what-is-llmo に追加 | 1記事 | #188, #193 |
| パイロット | 公開済み5記事に `dl-card` + AI相談導線を追加 | 5記事 | #194 |
| プレビュー画像導入 | 5記事の `dl-card` にExcelプレビュー画像を追加 | 5記事 | #202 |
| batch2 | 9サンプルを新規生成し10記事へ展開 | 10記事 | #205、修正 #207・#209 |
| batch3 | tagline / excel-ai / data-analysis の3サンプルを追加 | 3記事 | #212 |

`_common.py` はbatch2の量産基盤整備で導入された(コミット `abcc49f`)。それより前の5本(パイロット)は `_common.py` を使わない旧実装が残っている。

各バッチとも、生成後にsolによるレビューでMedium/Low指摘が入り、修正コミットが追加されている(履歴は `git log --oneline -- scripts/downloads-gen/` で確認できる)。指摘の傾向はdocProps・印刷設定・freeze pane選択の整合が中心で、`_common.py` への集約はこれらの重複修正を1箇所にまとめる目的で行われた。
