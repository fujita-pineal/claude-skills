# claude-skills

## 概要

株式会社ピネアルが Claude Code の運用で使っている検収・文章規範・SEOコラム量産のスキル一式の公開版。
コーポレートサイト（https://pineal.co.jp/column/）のコラム記事の執筆に実際に使っているルールと手順を、社内固有の情報を取り除いて公開している。

収録範囲は次の4スキルと、その土台になっている文体ルールのファイル1本。

- 検収（verify）: 生成物を意図・形式・事実・受け手の4層でチェックする手順
- 日本語技術文章（japanese-tech-writing）: 技術文書・記事の文章規範と機械チェック
- SEOコラム量産（seo-column）: 記事の設計から執筆・図版・機械チェック・公開までのパイプライン
- Gemini 書き換え（gemini-rewrite）: Gemini が書き、Claude が原文と意味照合して指摘を戻すループで、記事の文体を人が書いたものへ寄せる

## 収録内容

| パス | 用途 | 入口コマンド |
|---|---|---|
| `rules/document-tone-rules.md` | 見出し・本文の文体判定基準（正本） | 他スキルから参照する。単体では実行しない |
| `skills/verify/SKILL.md` | 検収手順（V1形式・V2意図適合・V3事実整合・V4受け手印象） | 「検収して」「/verify」等の依頼で読む |
| `skills/verify/house-rules.md` | 検収チェックリストH1〜H8の正本 | `SKILL.md` のV1から参照される |
| `skills/verify/pptx_jp_wrap_check.py` | PPTXの日本語折り返し崩れの検査 | `python3 pptx_jp_wrap_check.py <file.pptx>` |
| `skills/japanese-tech-writing/SKILL.md` | 日本語技術文章の文章規範 | 技術文書・記事の執筆時に読む |
| `skills/japanese-tech-writing/scripts/njlint.sh` | 禁止語・翻訳調・無生物主語などの機械検査 | `njlint.sh --mode slide <file>` / `njlint.sh --mode prose --genre tech <file>` |
| `skills/seo-column/SKILL.md` | SEOコラム量産パイプラインの実行手順 | 新規記事執筆・図版追加・humanizeリライト時に読む |
| `skills/seo-column/docs/` | パイプライン定義・文体ガイド・図版設計・humanize適応表・DLサンプル制作の各正本 | `SKILL.md` から参照される |
| `skills/seo-column/scripts/` | frontmatter・文字数・リンク・禁止表現の機械チェック一式 | `python3 check-column.py` 等 |
| `skills/gemini-rewrite/SKILL.md` | Gemini 書き換えの手順（平文モード・記事モード） | 「geminiで書き直して」「geminiループ回して」で読む |
| `skills/gemini-rewrite/scripts/gemini_rewrite.py` | 平文1本を Gemini に書き直させる | `printf '%s' "$DRAFT" \| python3 gemini_rewrite.py --brief "..."` |
| `skills/gemini-rewrite/scripts/article_loop.py` | Markdown 記事を節ごとに書き換え、校閲モデルの指摘を戻すループ | `python3 article_loop.py <article.md> <outdir> --rounds 3` |

## インストール方法

スキルは `~/.claude/skills/` 配下に置くと Claude Code から認識される。ルールファイルは `~/.claude/rules/` に置く。

```bash
mkdir -p ~/.claude/skills ~/.claude/rules
ln -s /path/to/claude-skills/skills/verify ~/.claude/skills/verify
ln -s /path/to/claude-skills/skills/japanese-tech-writing ~/.claude/skills/japanese-tech-writing
ln -s /path/to/claude-skills/skills/seo-column ~/.claude/skills/seo-column
ln -s /path/to/claude-skills/skills/gemini-rewrite ~/.claude/skills/gemini-rewrite
ln -s /path/to/claude-skills/rules/document-tone-rules.md ~/.claude/rules/document-tone-rules.md
```

symlinkの代わりに `cp -r` でコピーしてもよい。その場合、元ファイルを更新しても反映されない点に注意する。

`seo-column` はディレクトリ構成（`content/column/`、`src/lib/content.ts` の `isPublishedColumnEntry()`、`scripts/check-column.py` 等）がAstro製サイト前提で書かれている。別のサイト構成で使う場合はパスの読み替えが要る。

## 各skillの使い方の要点

### verify（検収）

検収は次の順で進む。

1. 対象ファイルを確定する
2. AskUserQuestion（または相当する対話）で検収意図（本質的検収者・達成水準・スコープ外・致命条件・期待行動・追加受け手）を2回に分けて確認する
3. `artifact_scope`（external / internal / public / hiring）を確定する
4. V1形式、V2意図適合、V3事実整合、V4受け手印象の4層を判定する
5. 統合判定（pass / fail / needs_confirmation）を出す
6. 再検収の場合は前回指摘との解消状況を比較する

V1形式は `house-rules.md` のH1〜H8（レンダリング崩れ、文体、平易さ、出典、金額・機密の露出、表記統一、分量、ファイルの機械的整合）を1項目ずつ判定する。H2の文体判定は `rules/document-tone-rules.md` を必ず先に読む。

### japanese-tech-writing（日本語技術文章）

執筆・推敲の規範に加えて、機械チェックを備える。

```bash
skills/japanese-tech-writing/scripts/njlint.sh --mode slide <file>                # 資料: スライド・提案書・Slack投稿
skills/japanese-tech-writing/scripts/njlint.sh --mode prose --genre tech <file>   # 文章: 技術記事
skills/japanese-tech-writing/scripts/njlint.sh --mode prose --genre essay <file>  # 文章: エッセイ・note
skills/japanese-tech-writing/scripts/njlint.sh --mode prose --genre business <file> # 文章: レポート・議事録・企画書
```

検出結果はFailではなく要確認として扱い、直すか残すかを文脈で判断する。

### seo-column（SEOコラム量産）

Stage0からStage8までのパイプラインで記事を作る。

| Stage | 工程 | 出力 |
|---|---|---|
| 0 | 一次情報プール整備 | 事実カード |
| 1 | 記事ブリーフ設計（一次情報の割当・図版計画を執筆前に確定） | ブリーフ |
| 2 | 素材調達（スクショ・画像） | 画像 + 素材台帳 |
| 3 | 初稿執筆（図版はプレースホルダ） | 本文 |
| 4 | 図版生成（SVG直書き / drawio） | SVG + 本文への埋め込み |
| 5 | humanizeリライト | リライト版本文 |
| 6 | 機械チェック | OK/NG |
| 7 | レビュー担当者レビュー | PRマージ |
| 8 | 自動公開 | 公開 |

機械チェックの実行例。

```bash
python3 skills/seo-column/scripts/check-column.py          # frontmatter・文字数・リンク・禁止表現・混入文字
node skills/seo-column/scripts/check-linebreak.mjs          # 見出し<wbr>の不変条件
python3 skills/seo-column/scripts/check-link-matrix.py      # 内部リンク表と本文の一致
python3 skills/seo-column/scripts/test-check-column-alt.py  # check-column.py自体のテスト
python3 skills/seo-column/scripts/test-check-link-matrix.py # check-link-matrix.py自体のテスト
```

`check-column.py` の `FORBIDDEN` / `FORBIDDEN_WORD` はサンプル値。自分の運用に合わせて、既公開記事に無い実在クライアント名や引用禁止の架空企業名に置き換えて使う。

## 公開版と社内版の違い

- 検収ログへの書き戻し（`verify_log.py`）、受け手の人物知見の参照・更新（`brain_writeback.py`）の実装は社内リポジトリ側にあり、本公開版には含めない。判定手順（V1〜V4）とH1〜H8のチェックリストはそのまま収録している
- 社内では制作中の機械検査（DOM契約・スクリーンショット・レイアウト互換性の検査）を生成側スキルの専用ステップとして持たせ、`verify` は納品前の検収に専念させている。その生成側スキルの実装は本公開版には含めない
- consulting-pptx-skill（`gozen3ji/consulting-pptx-skill`、MIT）との突合結果をまとめた対応表は、社内の意思決定文脈に依存する記述が多いため非収録。突合で追加した項目自体は `house-rules.md`・`document-tone-rules.md` にそのまま反映済み
- SEOコラムの `outline.md`（進行管理表）、`link-matrix.md`（内部リンク表）、`primary-sources.md`（一次情報バンク）は案件固有の内容が濃いテーブルのため非収録。ファイルの役割は `skills/seo-column/SKILL.md` に一文で残している
- クライアント企業名・個人名は、実在の固有名詞から汎化した表現（「製造業A社」「レビュー担当者」等）に置き換えている。ルールの判定ロジック・ID・辞書・閾値・沿革の構造は変更していない

## ライセンス

MIT License。詳細は `LICENSE` を参照。

`skills/japanese-tech-writing/scripts/` の一部ファイルは coji/natural-japanese（v1.5.0、MIT License）を無改変で含む。取り込み範囲とバージョンは `skills/japanese-tech-writing/scripts/UPSTREAM.md` を参照。

## 出典

株式会社ピネアル CTO 藤田拳が、コーポレートサイト（https://pineal.co.jp/column/）の執筆に使用しているスキルの公開版。
