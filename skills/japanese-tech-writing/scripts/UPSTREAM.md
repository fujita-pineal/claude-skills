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
