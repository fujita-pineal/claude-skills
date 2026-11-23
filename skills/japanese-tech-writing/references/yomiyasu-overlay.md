# yomiyasu の取り込み範囲と、正本による打ち消し

2026-10-03、nanaism/yomiyasu から `scripts/yomiyasu_lint.py` だけを無改変で取り込んだ。
2026-11-17 に v3.1.0 へ更新し、依存する `markdown_visibility.py` もあわせて取り込んだ。
`njlint.sh` が lint.py と同じ対象に掛け、「比喩動詞と定型句」の節に出す。
出所とコミットは `../scripts/UPSTREAM.md` にある。

判定の正本は `~/.claude/rules/document-tone-rules.md` と `../SKILL.md` で、検出器の指摘と食い違うときは正本が勝つ。
findings はすべて要確認として扱う。yomiyasu の点数（v2.0.0 以降は JSON の `rule_penalty_score`）は使わない。
`--doc-type` は渡していない。種類を指定したときだけ当たる規則（`pause_comma`、`slide_comma` など）は出ない。

## 取り込んだ理由

lint.py は、口語の比喩動詞と締めの定型句をほとんど拾わない。

- 比喩動詞
  - 「地味に効く」「時間を溶かす」「静かに壊れる」「側に倒す」「1つずつ潰す」など
  - 抽象物が主語のときだけ当たるように、正規表現の前後条件で絞ってある
- 定型句
  - 「結論から言うと」「正直に言うと」「いかがでしたか」「ぜひ〜してみてください」
  - 辞書5「予告・締めの定型」のうち、njlint でゼロヒットだった語の一部を拾う

## 抑止している検出

抑止は `njlint_report.py` の `Y_ALWAYS_DROP` / `Y_SLIDE_DROP` / `Y_DROP_WORDS` で行う。

| 検出 | モード | 抑止の理由 |
|---|---|---|
| `unnatural_halfwidth_space` | すべて | 和欧文のあいだに半角空白を入れる手元の表記と逆 |
| `excess_list` | すべて | ネスト箇条書きを基本とする規範と衝突する。lint.py の `high_bullet_ratio` とも重複 |
| `excess_bold` | すべて | lint.py の `high_bold_density` と重複 |
| `trailing_colon` | すべて | 列挙・例示の前のコロンは可とする `../SKILL.md` の規範と衝突 |
| `sentence_end_repetition` | 資料 | 断片テキストの集合では文末の連続が成り立たない |
| `slop_vocabulary` の「正本」 | すべて | 運用側の規約語。`document-tone-rules.md` 自体が使っている |
| `slop_vocabulary` の「台帳」 | すべて | 運用側の規約語。請求台帳や素材台帳など、文字どおりの記録簿を指す |
| `calque` / `translated_term` の「版」 | すべて | 運用側の規約語。版番号、改版、旧版など、正本と配置ルール自体が使っている |

2026-10-03 に記事下書き2本と `document-tone-rules.md` へ掛けた実測では、抑止前のスコアが3本とも0点だった。
最も多いのは半角空白（記事2本で44件）で、「正本」も計12件あった。

2026-11-17 の v3.1.0 更新時に、note 記事8本とコラム4本へ v1.0.4 と v3.1.0 を掛けて比べた。
半角空白は v3.1.0 で0件になったが、上流が戻したときに備えて抑止は残す。
新しく出た規則は `katakana_term` 30件、`calque` 7件、`bold_label_list` 3件、`negative_parallelism_density` 3件、`translated_term` 1件。
`slop_vocabulary` は「台帳」9件、「正本」8件、「土台」2件で、`calque` のうち4件と `translated_term` の1件は「版」だった。

## 残している検出

- `metaphor_verb`、`slop_vocabulary`（「正本」以外）、`meta_filler`
- `negative_parallelism`
  - 「AではなくB」を行ごとに拾う。`../SKILL.md` は否定の根拠を一文添えれば可としているので、根拠の有無を見て判断する
- `emoji_prohibited`、`redundant_bracket`、`bold_not_rendered`
- `sentence_end_repetition`（文章モードのみ）
- v2.0.0 以降に増えた規則（v3.1.0 時点）
  - `katakana_term`: 辞書5「カタカナ盛り」と同じ扱いで要確認。内蔵の一覧はソリューション、シナジーなど31語
  - `calque`、`translated_term`、`renyo_noun`、`thin_evaluation`、`ai_phrase`、`metaphor_label`
  - `bold_label_list`: 太字の見出し語とコロンの箇条書き。トップレベルを短いラベル、詳細を1段下げる正本の箇条書きと同じ向き
  - `negative_parallelism_density`: 否定の対比が文書内に多いときの1件
  - `dash_decoration`、`dash_insertion`、`dash_list_ending`: 正本のダッシュ禁止と同じ向き
  - `heading_colon`、`short_summary_heading`、`cleft_list_ending`、`fragment_run`、`short_mochiron`、`instruction_residue`

`slop_vocabulary` には「温度感」「土台」「装置」なども入っている。
商談の温度感や製造業の装置のように文字どおりの意味で使っている箇所は、そのまま残してよい。

## 採らなかったもの

- `SKILL.md` 本体（書き直しの手順）
  - 冒頭で「他の日本語校正スキルと同じ環境では指示が干渉する」と自ら書いており、発動条件も広い
  - 書き直しは gemini-rewrite と humanize が担っている
- `references/slop-catalog.md`
  - 「single source of truth の訳の正本を言い換える」という項目が規約語と衝突する
- `references/domains/essay.md`
  - 「素直な実感と身体性を残す」は、2026-08-29 に unslop の soul を不採用にしたのと同じ理由で採らない
- `scripts/yomiyasu_diff.py`
  - 書き直し前後の差分検査で、gemini-rewrite の意味照合と役割が重なる
