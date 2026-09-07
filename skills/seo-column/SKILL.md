---
name: seo-column
description: pineal-corp-site の SEOコラム(content/column/*.md)を量産・保守するパイプラインv3の実行手順。記事ブリーフ設計、一次情報の収集と割当、初稿執筆、図版(SVG直書き / drawio BPMN)の設計と生成、humanizeリライト、機械チェック、内部リンク管理、日次自動公開の運用を扱う。次の場合に使う - (1)新しいコラム記事を書く・バッチ執筆する (2)既存コラムに図版を追加する (3)humanizeリライトをかける (4)週次リンクパッチを当てる (5)コラムの進捗・公開予定を確認する (6)content/column/ 配下を編集する (7)コラムのプレビューやレビュー依頼に対応する
---

# SEOコラム パイプラインv3

49本の新規記事+公開済み1本を、日次1本で自動公開していく量産プログラムの実行手順。

**このskillは手順だけを持つ。設計の正本はすべて `skills/seo-column/docs/` にある。** 内容をこのファイルに複製しないこと。過去にカテゴリ語彙をsubagent間で複製して実際にドリフト事故を起こしている。

`outline.md`・`link-matrix.md`・`primary-sources.md` は案件固有の進行管理表・内部リンク表・一次情報バンクであり、内容がサイト運用に強く依存するため本公開版には収録していない。自分のサイトで使う場合は同じ役割の表を別途用意すること。

## 正本の所在

| 読むもの | いつ読むか |
|---|---|
| `skills/seo-column/docs/pipeline-v3.md` | 常に。工程の定義とモデル割当 |
| `docs/seo-column/outline.md`(非収録) | 記事の構成・公開予定日・進捗ステータス(進行管理表を兼ねる。案件固有のためこの公開版には無い) |
| `skills/seo-column/docs/style-guide.md` | 執筆時。frontmatter仕様・トーン・構成・カテゴリ正規語彙12種・CTA |
| `skills/seo-column/docs/figure-design.md` | 図版の要否判断・図種カタログ・BPMN規約・デザイン規約 |
| `skills/seo-column/docs/humanize-column.md` | humanizeリライト時。適応元のNG辞書は社内リポジトリ側にあり、本公開版には含めない |
| `docs/seo-column/link-matrix.md`(非収録) | 内部リンク指定・ピラー記事の特定・未来リンクのコメントアウト対象。列は記事slug・リンク先・公開日・被リンク数など、案件固有の表 |
| `docs/seo-column/primary-sources.md`(非収録) | 一次情報バンク。事例・数値の出典と、社内ヒアリングで得た一次情報の回答を記事slugごとに紐付けた表 |
| `skills/seo-column/docs/dl-samples.md` | DLサンプル(コラム記事のダウンロード資料xlsx)制作時。`scripts/downloads-gen/` の手順・品質ゲート・過去バッチの経緯 |

## 作業の入口

| やること | 入るStage |
|---|---|
| 新規記事をバッチ執筆する | Stage 0 →(初回のみ)→ 1 → 2 → 3 → 4 → 5 → 6 |
| 既存記事に図版を足す | Stage 1(図版計画のみ) → 2 → 4 → 6 |
| humanizeだけかける | Stage 5 → 6 |
| 週次リンクパッチ | 下記「週次リンクパッチ」 |
| 進捗を確認する | `outline.md`(非収録・案件固有の進行管理表)のステータス列を読む |

## 工程とモデル割当

**モデルの指定は守ること。** 設計と作図の質がそのまま成果物に出るので、そこに上位モデルを置いている。

| Stage | 工程 | モデル | 出力 |
|---|---|---|---|
| 0 | 一次情報プール整備 | haiku(並列) | `docs/seo-column/facts/*.md` |
| 1 | 記事ブリーフ設計 | **fable**(上限時 opus) | `docs/seo-column/briefs/{slug}.md` |
| 2 | 素材調達(スクショ・画像) | haiku(並列) | `content/images/column/{slug}/` + 素材台帳 |
| 3 | 初稿執筆 | sonnet | `content/column/{slug}.md`(図版はプレースホルダ) |
| 4 | 図版生成 | **opus** | SVG / drawio + 本文への埋め込み |
| 5 | humanizeリライト | sonnet | リライト版本文 |
| 6 | 機械チェック | — | `python3 scripts/check-column.py` |
| 7 | レビュー担当者レビュー | レビュー担当者 | PR単位 |
| 8 | 自動公開 | GitHub Actions | 人手ゼロ |

各Stageの詳細な入出力仕様は `pipeline-v3.md` を読むこと。

### Stage 1 が最重要

一次情報の割当と図版計画を**執筆前に**確定する。ここを飛ばして書き始めると、図が本文の装飾に落ちてv2の失敗を繰り返す。

図の要否は `figure-design.md` の基準で判断する。**図版0点も正解**。ブリーフに理由を書けば通る。「全記事に最低1点」というノルマはv3で廃止した。

### Stage 4 の作図

- 概念図・比較マトリクス・ステップ図・Before/After・時系列 → **SVG直書き**
- BPMN業務フロー・システム構成図 → **drawio**。ソースは `docs/seo-column/figures/{slug}/fig-N.drawio`(案件固有・非収録)、書き出しは:
  ```bash
  scripts/drawio-export.sh {slug} N
  ```
- 書き出したSVGは**必ずブラウザで開いて目視確認する**。日本語の字幅で枠からはみ出す事故が起きやすい
- 本文への埋め込みは**自分自身へのリンクで包む**。モバイルで図内の文字が読めないため、タップで原寸を開けるようにする

  ```markdown
  [![alt文](/images/column/{slug}/fig-1.svg)](/images/column/{slug}/fig-1.svg)

  *図1: 図から読み取ってほしい結論*
  ```

## 絶対に守ること

- **数値の捏造禁止。** 出典が辿れない数字は本文にも図版にも書かない
- **クライアント実名は既公開の `content/cases/` `content/topics/` に載っている範囲のみ。** 新規の実名出しは先方承認が要る。迷ったら「製造業の大手企業で」等に匿名化する
- **実名不可の企業名リスト、架空企業名リストは `check-column.py` の `FORBIDDEN` 定数を参照。自分のサイトの実在クライアント名・架空企業名に置き換えて使うこと**
- 個別契約額・個人実名は記事に書かない(役職・立場の表記は可)
- 正式社名は「**株式会社ピネアル**」(前株)。「ピネアル株式会社」は誤記
- 実名を出す記事は、先方担当者承認済みの表現(研修・プログラム等)のみ使う
- カテゴリは `style-guide.md` 補足の**正規語彙12種から選ぶ**。勝手に増やさない

## 公開の制御

公開日の制御は **`publishedDate` の未来日付フィルタ**で行う。`src/lib/content.ts` の `isPublishedColumnEntry()` がJST基準で未来の記事を一覧・詳細・sitemapから除外する。全記事を未来日付のまま `main` にマージしてよい。

- `status: draft` は「公開日を過ぎた記事を緊急非公開にする」ための手段。量産記事のfrontmatterには付けない
- 毎朝 JST 6:00 に `.github/workflows/daily-publish.yml` がフルビルド+デプロイして、その日付になった記事を公開する。追加のセットアップは不要
- ローカルで未来記事を見るには `SHOW_FUTURE_COLUMNS=1 npm run dev`。このフラグをCI本番ビルドに設定しないこと

## 内部リンク

3層構造(事業ページ ← ピラー記事13本 ← 個別記事37本)。1記事あたり本文内リンク3〜5本。指定は `link-matrix.md` を見る。ピラーは原則カテゴリ1本だが、カテゴリ12だけ第2ピラー `what-is-ai-agent` を置いている。

**公開日が自分より後の記事へのリンクは必ずコメントアウトする。** そのまま出すと公開直後に404になる。

```markdown
<!-- [AIコンテンツマーケティング](/column/ai-content-marketing-guide/) -->
```

`scripts/check-column.py` が生リンクの公開順を検査して弾く。

### 週次リンクパッチ

1. `outline.md` の公開予定日と今日を比べ、公開済みになった記事を特定する
2. その記事を指すコメントアウトを本文で有効化する
3. `link-matrix.md` の未来参照リストから該当行を消す
4. `python3 scripts/check-link-matrix.py` で表と本文の一致を確認する。被リンク数が変わったら関係表とセルフチェック結果の両方を直す(チェッカーが両方を実測と照合する)
5. `python3 scripts/check-column.py` → PR

このチェッカーは**リンク先の公開日が今日に追いついたのにコメントアウトのままの参照をNGにする**。日付が進むだけで成立する検査なので、push時の `ci.yml` に加えて毎朝の `daily-publish.yml` でも走らせている(デプロイの後段に置いてあるため当日の公開は止まらない)。`公開済みリンクがコメントアウトのまま` が出たらパッチの時期が来たという合図。

## 検証

```bash
python3 scripts/check-column.py          # frontmatter・文字数・リンク・禁止表現・混入文字
npm run build                            # 通常ビルド(未来記事は除外される)
SHOW_FUTURE_COLUMNS=1 npm run build      # 未来記事込みでビルドが通るか
node scripts/check-linebreak.mjs         # 見出し<wbr>の不変条件(助詞行頭・数字複合語の分離)。build後に実行
python3 scripts/check-link-matrix.py     # link-matrix.mdと本文の内部リンクの一致(欠落・マーカー・被リンク数・前方参照)
python3 scripts/test-check-link-matrix.py # 上のチェッカー自体のミューテーションテスト。checkerを直したら回す
```

プレビューURLは **末尾スラッシュなし**。`/column/what-is-llmo` は200、`/column/what-is-llmo/` は404になる。

## 過去に踏んだ事故

同じ轍を踏まないこと。

- **SVGの `<text>` 内に `<br/>` を書いた** → HTMLパーサーがSVGを打ち切り、以降が生テキストとして画面に散らばった。改行は `<text>` を分けるか `<tspan>`
- **SVGで `class` と `fill` 属性を併用した** → CSSルールがpresentation attributeに勝ち、白抜き文字が黒く潰れた。インラインの `style="fill:#fff"` を使う
- **`drawio --export` を直接叩いた** → SVGの背景が透過で書き出され、ダークモードで図が読めない。`scripts/drawio-export.sh` を使う
- **outlineのステータス一括更新でslugの部分一致により31節を書き換えた** → `### No.(\d+) — ` を鍵にする
- **カテゴリ語彙がsubagent間でドリフトした**(「04 広告クリエイティブ」「広告クリエイティブ」等) → 正規語彙12種から選ばせ、チェッカーで検査する
- **キリル文字が混入した**(「публиковать」) → チェッカーがキリル/ハングル/タイ/アラビア文字を検出する

## 進捗の記録

記事を書き終えたら `outline.md` の該当節のステータスを更新する。この表が進行管理表を兼ねている。
