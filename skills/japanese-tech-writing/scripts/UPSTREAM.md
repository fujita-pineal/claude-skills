# ベンダリング元

`lint.py` / `textcore.py` / `outline.py` / `terms.py` と
`../references/` の `translationese.md` / `readability-antipatterns.md` / `readability-principles.md` は、
次の upstream から**無改変で**コピーしたものです。

| 項目 | 値 |
|---|---|
| リポジトリ | https://github.com/coji/natural-japanese |
| バージョン | v1.5.0 |
| コミット | 9a78a42964096da509b8f3e011f0085a5f080151 |
| コミット日時 | 2026-09-04 20:45:42 +0900 |
| ライセンス | MIT（`LICENSE-natural-japanese`、Copyright (c) 2026 coji） |
| 取り込み日 | 2026-09-04 |

## 無改変で置く理由

upstream が更新されたとき `diff` がそのまま効くようにするためです。
運用側の正本と食い違う記述は、ファイルを書き換えずに
`../references/natural-japanese-overlay.md` で打ち消しています。

## 更新手順

1. upstream を clone し、上記6ファイルを再コピーする
2. `natural-japanese-overlay.md` の「衝突箇所の指定」の行番号と引用が、まだ実際の記述と合っているか確認する
3. `lint.py --help` の検出カテゴリに増減がないか確認し、増えていれば `njlint.sh` の `SLIDE_DROP` / `ALWAYS_DROP` を見直す
4. 本 UPSTREAM.md のコミットとバージョンを更新する
5. `njlint.sh --mode slide` と `--mode prose` を既存の成果物1件ずつに掛け、`nominal_ending`（体言止め）が「抑止した検出」側に出ることを実測する。無効化は `njlint_report.py` の `ALWAYS_DROP` で行っており、upstream の `lint.py` 側の変更では外れないことを確認する

## 取り込まなかったもの

upstream の `SKILL.md` 本体、`references/writing-constitution.md`、`references/eval-rubric.md`、
`references/forbidden-patterns.md`、`references/diagnose.md`、`references/revision-guide.md`、
`references/genre-notes.md`、`references/examples.md`、`references/manual-checklist.md`、
`scripts/semantic.py`、`scripts/calibrate.py`、`assets/`。

理由は `natural-japanese-overlay.md` の「採らなかったもの」を参照してください。

## yomiyasu（2本目のベンダリング）

`yomiyasu_lint.py` と、それが import する `markdown_visibility.py` は、次の upstream の `skills/yomiyasu/scripts/` から**無改変で**コピーしたものです。
`njlint_report.py` が import して使い、抑止は `njlint_report.py` 側で行います。
`yomiyasu_lint.py` は隣の `../references/lists/` があれば語の一覧をそこから読み、なければ内蔵の一覧を使います。手元には置かず、内蔵の一覧で動かしています。

| 項目 | 値 |
|---|---|
| リポジトリ | https://github.com/nanaism/yomiyasu |
| バージョン | v3.1.0（`.claude-plugin/plugin.json`） |
| コミット | db78b9bc5e868549b517a037df7a4d1c93edac23 |
| コミット日時 | 2026-11-12 09:28:31 +0900 |
| ライセンス | MIT（`LICENSE-yomiyasu`、Copyright (c) 2026 nanaism）。同梱の Unicode 由来データは `LICENSE-yomiyasu-unicode`（上流の `UNICODE-LICENSE.txt`） |
| 取り込み日 | 2026-10-03（v1.0.4）、2026-11-17（v3.1.0 へ更新） |

更新手順:

1. upstream を clone し、`skills/yomiyasu/scripts/` の `yomiyasu_lint.py` と `markdown_visibility.py` を再コピーする。`LICENSE` と `UNICODE-LICENSE.txt` に差分があれば `LICENSE-yomiyasu` / `LICENSE-yomiyasu-unicode` も差し替える
2. `rule` の種類に増減がないか `grep -n '"rule"' yomiyasu_lint.py` で確認し、増えていれば `njlint_report.py` の `Y_ALWAYS_DROP` / `Y_SLIDE_DROP` を見直す
3. `slop_vocabulary`、`calque`、`translated_term` が手元の規約語を名指ししていないか、既存の記事数本に掛けて確認し、していれば `Y_DROP_WORDS` に足す
4. 本節のコミットとバージョンを更新する
5. `njlint.sh --mode prose` を既存の記事1件に掛け、`Y_DROP_WORDS` の語が「抑止した検出」側に出ることを実測する

取り込み範囲と抑止の理由は `../references/yomiyasu-overlay.md` を参照してください。

## 参照・採用元（選択採用。無改変のベンダリングではない）

上の `coji/natural-japanese` とは管理の仕方が違う。
ここに挙げるものは、スクリプトではなく規範文の出所であり、更新手順（上書きコピー）の対象にしない。
上流が更新されたら差分を読み、採る行だけを手で `SKILL.md` の既存節へ統合する。

| 出所 | リビジョン | 取得日 | ライセンス | 置き場所と採用範囲 |
|---|---|---|---|---|
| k16shikano gist `fd287c3133457c4fd8f5601d34aa817d`（japanese-tech-writing） | 8f2d576（2026-09-09） | 2026-09-20 | Unlicense | `../SKILL.md` の参照元。手元版を基準に、追加行だけを既存節へ統合した |
| cursor/plugins `pstack/skills/unslop/SKILL.md`（https://github.com/cursor/plugins/tree/main/pstack/skills/unslop） | 99559f2（2026-08-02） | 2026-08-30 | MIT（`LICENSE-pstack`、Copyright (c) 2026 Lauren Tan） | `../SKILL.md` の「LLM っぽい表現の禁止」と「冗長の排除」へ、6項目を日本語で書き直して統合した |

### gist から採ったもの（2026-09-20）

- 段落と論証の構成: 概念の初出で種別を先に示す、対比定義で述部を揃える
- 読み手の負荷の管理: 順読みで一段ずつ増やす、複数媒体の説明の分担
- 冗長の排除: 命題が違えば繰り返しではない、冗長を文字数で判定しない（中間段階の省略・一文化・並列のまとめを条件付きに置換）
- 演出の抑制: 翻訳調の述語の診断手順（二段判定）

### gist から採らなかったもの、変えたもの

- 「翻訳調の比喩と擬人化の禁止」節の新設: 擬人化と口語比喩の禁止は正本 R5 の再掲になるため、診断手順だけを「演出の抑制」に統合した。「効く」「刺さる」などの語単独の禁止リストは作らない
- 修正例「推敲の軸が線形に取り出せる」: 元の文にない意味を足しているため不採用
- イ形容詞＋「です」の一律禁止: 代案の「でしょう」「である」が確定性と敬体を変えるため、「視点と語り」に文脈確認の観点として置いた
- 「弱い緩和と称賛」「接続詞の連打」の語の列挙: 正本の辞書5 が持つため再掲しない（2026-09-19）
- description と license の frontmatter: 手元版を維持

### unslop から採ったもの（2026-08-30）

| 手元の項目 | 上流の項目（99559f2 での番号と名前） |
|---|---|
| 名指しのない出典 | 5 Vague attributions |
| ラベルの復唱 | 16 Inline-header lists |
| 接続詞代わりのコロン | 14 Colon overuse |
| 意味のない範囲表現 | 12 False ranges |
| 同じ対象の言い換えの連発 | 11 Synonym cycling |
| どの文書にも置ける文 | 27 Say what it does, not how it feels |

- 英語の規則を日本語の文章向けに書き直し、日本語の例を足した
- 「ラベルの復唱」「接続詞代わりのコロン」「どの文書にも置ける文」の例には、上流の例を訳したものを含む
- MIT License の条件に従い、著作権表示と許諾文を `LICENSE-pstack` に置く
- リビジョンは、取り込み日の時点で上流の最新だったコミット

### unslop から採らなかったもの

- 「Adding soul」の節と、上の6項目以外の項目

### 手元にしかなく、上流の更新で消してはならないもの

- 「整形」節、正本と辞書5 への従属の記述、「機械検査（納品前）」節、unslop 由来の6項目（名指しのない出典、ラベルの復唱、接続詞代わりのコロン、意味のない範囲表現、言い換えの回し、どの文書にも置ける文）
- 山場の先出しを個別論点内に限定する記述、約束した論点の3択処理
