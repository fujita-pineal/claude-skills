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

## 取り込まなかったもの

upstream の `SKILL.md` 本体、`references/writing-constitution.md`、`references/eval-rubric.md`、
`references/forbidden-patterns.md`、`references/diagnose.md`、`references/revision-guide.md`、
`references/genre-notes.md`、`references/examples.md`、`references/manual-checklist.md`、
`scripts/semantic.py`、`scripts/calibrate.py`、`assets/`。

理由は `natural-japanese-overlay.md` の「採らなかったもの」を参照してください。

## 参照・採用元（選択採用。無改変のベンダリングではない）

ここに挙げるものは、スクリプトではなく規範文の出所です。
上書きコピーの対象にせず、上流の差分を読んで、採る行だけを `../SKILL.md` へ統合します。

| 出所 | リビジョン | 取得日 | ライセンス | 採用範囲 |
|---|---|---|---|---|
| cursor/plugins `pstack/skills/unslop/SKILL.md`（https://github.com/cursor/plugins/tree/main/pstack/skills/unslop） | 99559f2（2026-08-02） | 2026-08-30 | MIT（`LICENSE-pstack`、Copyright (c) 2026 Lauren Tan） | `../SKILL.md` の「LLM っぽい表現の禁止」と「冗長の排除」へ、6項目を日本語で書き直して統合した |

### unslop から採ったもの

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
