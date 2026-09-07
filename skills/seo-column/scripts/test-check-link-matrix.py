#!/usr/bin/env python3
"""check-link-matrix.py のミューテーションテスト。

`scripts/fixtures/check-link-matrix/` の固定fixture(本番と同じ構造の最小データ)を
一時ディレクトリへコピーし、1件ずつ壊してからチェッカーを回す。壊したのに exit 0 が
返ったら、その不変条件には穴がある。

各変異は `expect` に「その変異が出すべきNGの断片」を持つ。単に何かがNGになった
だけでは合格にしない。狙った検査を消しても別のエラーでテストが緑になる事故を防ぐ。

本番の docs をfixtureにすると、正常な週次リンクパッチが変異の対象文字列を消して
テストが自壊する(PR #213のレビューで指摘された)。fixtureを固定してあるので
本番データがどう変わってもこのテストは安定して回る。

使い方: python3 scripts/test-check-link-matrix.py
全変異が期待どおり検出できれば exit 0、取りこぼしがあれば exit 1。
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/check-link-matrix.py"
FIXTURE = ROOT / "scripts/fixtures/check-link-matrix"
LM = "docs/seo-column/link-matrix.md"
OL = "docs/seo-column/outline.md"
ART = "content/column/article-b.md"
ARTC = "content/column/article-c.md"
SG = "docs/seo-column/style-guide.md"
PD = "content/column/pillar-d.md"
PA = "content/column/pillar-a.md"
AE = "content/column/article-e.md"
DIST_AI = "dist/ai/index.html"
BASE_TODAY = "2026-01-02"

ROGUE = """---
title: "計画外の記事"
publishedDate: 2026-01-02
---

本文。
"""

# name: 変異の説明 / expect: 出るべきNGの断片 / edits: 置換 / delete: 削除 / create: 新規
# / rmtree: ディレクトリ削除 / rename: 改名 / forbid: 出てはいけないNGの断片
# / day: 基準日(省略時 BASE_TODAY)
MUTATIONS = [
    {"name": "関係表からリンクを削る", "expect": "関係表に未記載のリンク", "edits": [
        (LM, "`pillar-a`, `article-c`※未公開(コメントアウト), `/ai` | 1 |", "`pillar-a`, `/ai` | 1 |")]},
    {"name": "未公開マーカーを外す", "expect": "※未公開マーカーが欠落", "edits": [
        (LM, "`article-c`※未公開(コメントアウト)", "`article-c`")]},
    {"name": "未公開マーカーの表記を崩す", "expect": "本文リンク先セルの書式が不正", "edits": [
        (LM, "`article-c`※未公開(コメントアウト)", "`article-c`※未公開かもしれない")]},
    {"name": "前方参照の日付を1日ずらす", "expect": "前方参照一覧の日付ズレ", "edits": [
        (LM, "→ `article-c`(01-03)", "→ `article-c`(01-04)")]},
    {"name": "前方参照行を1件削除する", "expect": "前方参照一覧に未記載", "edits": [
        (LM, "- `pillar-d`(01-04) → `article-e`(01-05)\n", "")]},
    {"name": "有効化済みリンクを前方参照へ再追加する", "expect": "前方参照一覧の余分な行", "edits": [
        (LM, "- `pillar-d`(01-04) →", "- `article-c`(01-03) → `article-b`(01-02)\n- `pillar-d`(01-04) →")]},
    {"name": "前方参照のリンク元日付を改竄する", "expect": "前方参照一覧の日付ズレ", "edits": [
        (LM, "- `article-b`(01-02) →", "- `article-b`(01-01) →")]},
    {"name": "関係表のslugを公開カレンダーから外す",
     "expect": "outlineの公開カレンダーにない: article-e-x", "edits": [
        (LM, "| article-e | 02 |", "| article-e-x | 02 |")]},
    {"name": "関係表に重複行を作る", "expect": "関係表に重複行", "edits": [
        (LM, "| article-e | 02 |", "| article-e | 02 |  | `pillar-d`, `/ai` | 1 |\n| article-e | 02 |")]},
    {"name": "関係表の行内でリンク先を重複させる", "expect": "関係表の行内でリンク先が重複", "edits": [
        (LM, "| article-e | 02 |  | `pillar-d`,", "| article-e | 02 |  | `pillar-d`, `pillar-d`,")]},
    {"name": "関係表の被リンク数を改竄する", "expect": "被リンク数の不一致", "edits": [
        (LM, "| pillar-a | 01 アルファ | ● | `/ai`, `/cases/case-x` | 4 |",
         "| pillar-a | 01 アルファ | ● | `/ai`, `/cases/case-x` | 3 |")]},
    {"name": "関係表のピラー列を不正な記号にする", "expect": "関係表のピラー列が不正", "edits": [
        (LM, "| pillar-a | 01 アルファ | ● |", "| pillar-a | 01 アルファ | ○ |")]},
    {"name": "関係表のカテゴリをoutlineとズラす", "expect": "カテゴリ不一致: article-b", "edits": [
        (LM, "| article-b | 01 |", "| article-b | 03 |")]},
    {"name": "実在しないslugへのリンクを本文と表へ同期追加する",
     "expect": "関係表のリンク先が実在しないslug", "edits": [
        (ART, "を参照。", "を参照。[記事X](/column/ghost/)も参照。"),
        (LM, "`pillar-a`, `article-c`※未公開(コメントアウト), `/ai`",
         "`pillar-a`, `ghost`, `article-c`※未公開(コメントアウト), `/ai`")]},
    {"name": "本文リンクを2本に減らす", "expect": "本文リンク先の本数が3〜5本の範囲外", "edits": [
        (LM, "`article-c`※未公開(コメントアウト), `/ai` | 1 |", "`article-c`※未公開(コメントアウト) | 1 |")]},
    {"name": "セルフチェック1の総記事数を改竄する", "expect": "セルフチェック1: 総記事数の表記", "edits": [
        (LM, "**PASS。** 5記事すべてが", "**PASS。** 4記事すべてが")]},
    {"name": "セルフチェック1の最小リストから1件削る", "expect": "最小リストの欠落", "edits": [
        (LM, "`article-b`, `article-c`, `article-e`, `pillar-d`", "`article-b`, `article-e`, `pillar-d`")]},
    {"name": "セルフチェック2の被リンク数を改竄する", "expect": "セルフチェック2: カテゴリ01 pillar-a", "edits": [
        (LM, "pillar-a(4)", "pillar-a(3)")]},
    {"name": "セルフチェック2のカテゴリ行を削除する", "expect": "セルフチェック2: カテゴリ行=", "edits": [
        (LM, "| 02 ベータ | pillar-d(1) | article-e(1) | ○ |\n", "")]},
    {"name": "セルフチェック2のカテゴリ行を複製する", "expect": "カテゴリ行が重複している", "edits": [
        (LM, "| 02 ベータ | pillar-d(1) | article-e(1) | ○ |",
         "| 02 ベータ | pillar-d(1) | article-e(1) | ○ |\n| 02 ベータ | pillar-d(1) | article-e(1) | ○ |")]},
    {"name": "セルフチェック2の判定列を反転する", "expect": "カテゴリ02の判定=×", "edits": [
        (LM, "| 02 ベータ | pillar-d(1) | article-e(1) | ○ |", "| 02 ベータ | pillar-d(1) | article-e(1) | × |")]},
    {"name": "セルフチェック2の欄内でslugを重複させる", "expect": "ピラー欄にslugの重複がある", "edits": [
        (LM, "| 01 アルファ | pillar-a(4)", "| 01 アルファ | pillar-a(4)/pillar-a(4)")]},
    {"name": "セルフチェック2のPASS見出しを削除する", "expect": "「PASS(全Nカテゴリ)」の見出しが見つからない", "edits": [
        (LM, "**PASS(全2カテゴリ)。**\n", "")]},
    {"name": "セルフチェック2のPASS見出しをコメントアウトする",
     "expect": "「PASS(全Nカテゴリ)」の見出しが見つからない", "edits": [
        (LM, "**PASS(全2カテゴリ)。**", "<!-- **PASS(全2カテゴリ)。** -->")]},
    {"name": "ピラーの被リンクが非ピラーを下回る状態にする(三者同期)",
     "expect": "を下回っている", "edits": [
        (LM, "| pillar-d | 02 ベータ | ● |", "| pillar-d | 02 ベータ |  |"),
        (LM, "| 02 ベータ | pillar-d(1) | article-e(1) | ○ |",
         "| 02 ベータ | (なし) | article-e(1)/pillar-d(1) | × |"),
        (OL, "| 2026-01-04 | 4 | KW-D | pillar-d | 02 ベータ | ● |",
         "| 2026-01-04 | 4 | KW-D | pillar-d | 02 ベータ | |"),
        (OL, "`pillar-d` / 公開予定日: 2026-01-04 / カテゴリ: 02 ベータ / 事業: `/ai` / ピラー: Yes(02)",
         "`pillar-d` / 公開予定日: 2026-01-04 / カテゴリ: 02 ベータ / 事業: `/ai` / ピラー: No")]},
    {"name": "主ピラーをカテゴリ内に2本置く(三者同期)", "expect": "主ピラー(●)が2本", "edits": [
        (LM, "| article-b | 01 |  |", "| article-b | 01 | ● |"),
        (LM, "| 01 アルファ | pillar-a(4)/article-c(1・第2ピラー) | article-b(1) | ○ |",
         "| 01 アルファ | pillar-a(4)/article-b(1)/article-c(1・第2ピラー) | (なし) | ○ |"),
        (OL, "| 2026-01-02 | 2 | KW-B | article-b | 01 アルファ | |",
         "| 2026-01-02 | 2 | KW-B | article-b | 01 アルファ | ● |"),
        (OL, "`article-b` / 公開予定日: 2026-01-02 / カテゴリ: 01 アルファ / 事業: `/ai` / ピラー: No",
         "`article-b` / 公開予定日: 2026-01-02 / カテゴリ: 01 アルファ / 事業: `/ai` / ピラー: Yes(01)")]},
    {"name": "凡例の第2ピラー宣言を消す", "expect": "凡例の第2ピラー宣言が0件", "edits": [
        (OL, "**例外としてカテゴリ01のみ第2ピラー `article-c` を置く**", "**第2ピラーは置かない**")]},
    {"name": "公開カレンダーの第2ピラー印を消す", "expect": "ピラー指定がカレンダーと詳細節で不一致: article-c", "edits": [
        (OL, "| article-c | 01 アルファ | ●(第2) |", "| article-c | 01 アルファ |  |")]},
    {"name": "公開カレンダーのピラー列を不正な記号にする", "expect": "公開カレンダーのピラー列が不正", "edits": [
        (OL, "| pillar-a | 01 アルファ | ● |", "| pillar-a | 01 アルファ | ○ |")]},
    {"name": "公開カレンダーの行を複製する", "expect": "公開カレンダーに重複slug", "edits": [
        (OL, "| 2026-01-05 | 5 | KW-E | article-e | 02 ベータ | |",
         "| 2026-01-05 | 5 | KW-E | article-e | 02 ベータ | |\n| 2026-01-05 | 5 | KW-E | article-e | 02 ベータ | |")]},
    {"name": "未来日の記事に「公開済」表記を付ける", "expect": "宣言していないslugに「(公開済)」印がある", "edits": [
        (OL, "| 2026-01-05 | 5 |", "| 2026-01-05(公開済) | 5 |"),
        (OL, "- slug: `article-e` / 公開予定日: 2026-01-05 / カテゴリ: 02 ベータ / 事業: `/ai` / ピラー: No / 記事タイプ: 手順 / ステータス: 未着手\n", "")]},
    {"name": "詳細節のピラー指定をNoへ戻す", "expect": "ピラー指定がカレンダーと詳細節で不一致: article-c", "edits": [
        (OL, "ピラー: Yes(01・第2ピラー)", "ピラー: No")]},
    {"name": "詳細節のピラー番号をカテゴリとズラす", "expect": "詳細節のピラー番号がカテゴリと不一致", "edits": [
        (OL, "ピラー: Yes(02)", "ピラー: Yes(01)")]},
    {"name": "詳細節のピラー表記を不正な文字列にする", "expect": "詳細節のピラー表記が不正", "edits": [
        (OL, "ピラー: Yes(02)", "ピラー: YesWhatever")]},
    {"name": "詳細節からslug行を1件落とす", "expect": "公開カレンダーにあるが詳細節にないslug: article-e", "edits": [
        (OL, "- slug: `article-e` / 公開予定日:", "- 公開予定日:")]},
    {"name": "本文で有効リンクとコメントアウトを重複させる",
     "expect": "本文で有効リンクとコメントアウトが重複", "edits": [
        (ART, "本文。詳しくは[記事A](/column/pillar-a/)を参照。",
         "本文。詳しくは[記事A](/column/pillar-a/)を参照。\n\n<!-- [記事A](/column/pillar-a/) -->")]},
    {"name": "frontmatterの公開日をoutlineとズラす", "expect": "publishedDate がoutlineと不一致", "edits": [
        (ART, "publishedDate: 2026-01-02", "publishedDate: 2026-01-01")]},
    {"name": "frontmatterの公開日を本文へ逃がす", "expect": "publishedDate が0件ある", "edits": [
        (ART, "publishedDate: 2026-01-02\n---", "---"),
        (ART, "を参照。", "を参照。\n\npublishedDate: 2026-01-02")]},
    {"name": "frontmatterの公開日に余計な文字を付ける", "expect": "publishedDate が YYYY-MM-DD ではない", "edits": [
        (ART, "publishedDate: 2026-01-02", "publishedDate: 2026-01-02oops")]},
    {"name": "未公開リンクを3点同時に有効化する", "expect": "未公開リンクが有効化されている", "edits": [
        (ART, "<!-- [記事C](/column/article-c/) -->", "[記事C](/column/article-c/)"),
        (LM, "`article-c`※未公開(コメントアウト)", "`article-c`"),
        (LM, "- `article-b`(01-02) → `article-c`(01-03)\n", "")]},
    {"name": "公開日が到来した記事の実ファイルがない",
     "expect": "公開日が到来しているのに content/column/pillar-a.md がない",
     "delete": ["content/column/pillar-a.md"]},
    {"name": "計画外の記事を置く", "expect": "が関係表にない(計画外の記事)",
     "create": {"content/column/rogue.md": ROGUE}},
    {"name": "本文だけから事業ページのリンクを削る",
     "expect": "関係表にあるが本文にないリンク: article-b -> /ai", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。", "")]},
    {"name": "量産記事を既存記事へ再分類して制約を迂回する",
     "expect": "宣言していないslugに「(公開済)」印がある", "edits": [
        (OL, "| 2026-01-02 | 2 |", "| 2026-01-02(公開済) | 2 |"),
        (OL, "- slug: `article-b` / 公開予定日: 2026-01-02 / カテゴリ: 01 アルファ / 事業: `/ai` / ピラー: No / 記事タイプ: 解説 / ステータス: レビュー済み\n", ""),
        (LM, "`article-c`※未公開(コメントアウト), `/ai` | 1 |", "`article-c`※未公開(コメントアウト) | 1 |")]},
    {"name": "凡例の既存記事宣言を消す", "expect": "凡例の既存記事宣言が0件", "edits": [
        (OL, "- **既存記事**: `pillar-a`", "- 既存記事はない `pillar-a`")]},
    {"name": "凡例の第2ピラー宣言をコメントアウトする", "expect": "凡例の第2ピラー宣言が0件", "edits": [
        (OL, "**例外としてカテゴリ01のみ第2ピラー `article-c` を置く**",
         "<!-- **例外としてカテゴリ01のみ第2ピラー `article-c` を置く** -->")]},
    {"name": "凡例に矛盾する第2ピラー宣言を足す", "expect": "凡例の第2ピラー宣言が2件", "edits": [
        (OL, "## 公開カレンダー概要",
         "- 追記: **例外としてカテゴリ02のみ第2ピラー `article-e` を置く**\n\n## 公開カレンダー概要")]},
    {"name": "事業ページのパスを実在しないものにする", "expect": "関係表のリンク先パスが実在しない", "edits": [
        (LM, "| article-b | 01 |  | `pillar-a`, `article-c`※未公開(コメントアウト), `/ai` |",
         "| article-b | 01 |  | `pillar-a`, `article-c`※未公開(コメントアウト), `/aix` |")]},
    {"name": "正規マーカーの後ろに文字を足す", "expect": "本文リンク先セルの書式が不正", "edits": [
        (LM, "`article-c`※未公開(コメントアウト)", "`article-c`※未公開(コメントアウト)かもしれない")]},
    {"name": "リンク先をリンク構文でないただの文字列にする",
     "expect": "本文リンク先セルの書式が不正", "edits": [
        (LM, "| article-b | 01 |  | `pillar-a`, `article-c`※未公開(コメントアウト), `/ai` |",
         "| article-b | 01 |  | `pillar-a`, `article-c`※未公開(コメントアウト), banana |")]},
    {"name": "関係表の行をHTMLコメントで包む", "expect": "公開カレンダーのslugが関係表にない: article-e", "edits": [
        (LM, "| article-e | 02 |  | `pillar-d`, `pillar-a`(cross), `/ai` | 1 |",
         "<!-- | article-e | 02 |  | `pillar-d`, `pillar-a`(cross), `/ai` | 1 | -->")]},
    {"name": "関係表に自己リンクを足す", "expect": "関係表に自己リンクがある", "edits": [
        (LM, "| article-e | 02 |  | `pillar-d`,", "| article-e | 02 |  | `article-e`, `pillar-d`,")]},
    {"name": "公開カレンダーの日付に余計な文字を付ける", "expect": "公開カレンダーの日付セルが不正", "edits": [
        (OL, "| 2026-01-04 | 4 |", "| 2026-01-04oops | 4 |")]},
    {"name": "詳細節の公開予定日に余計な文字を付ける", "expect": "詳細節の公開予定日が YYYY-MM-DD ではない", "edits": [
        (OL, "`pillar-d` / 公開予定日: 2026-01-04", "`pillar-d` / 公開予定日: 2026-01-04oops")]},
    {"name": "暦として存在しない日付を書く", "expect": "日付として解釈できない", "edits": [
        (OL, "| 2026-01-04 | 4 |", "| 2026-02-30 | 4 |")]},
    {"name": "公開日がリンク先に追いついても週次パッチを当てない",
     "expect": "公開済みリンクがコメントアウトのまま", "day": "2026-01-05"},
    # --- 未執筆行(実ファイルがない計画上の行)にも効く検査 ---
    {"name": "未執筆行のマーカーと前方参照を同時に外す",
     "expect": "リンク先が未公開なのに※未公開マーカーがない", "delete": [PD], "edits": [
        (LM, "`article-e`※未公開(コメントアウト)", "`article-e`"),
        (LM, "- `pillar-d`(01-04) → `article-e`(01-05)\n", "")]},
    {"name": "未執筆行に不要なマーカーと前方参照を同時に足す",
     "expect": "リンク先が公開済みなのに※未公開マーカーが残っている", "delete": [PD], "edits": [
        (LM, "| pillar-d | 02 ベータ | ● | `pillar-a`(cross),",
             "| pillar-d | 02 ベータ | ● | `pillar-a`(cross)※未公開(コメントアウト),"),
        (LM, "- `pillar-d`(01-04) →", "- `pillar-d`(01-04) → `pillar-a`(01-01)\n- `pillar-d`(01-04) →")]},
    # --- リンク先セルの解釈 ---
    {"name": "コラム間リンクを/column/パス表記にする", "expect": "本文リンク先セルの書式が不正", "edits": [
        (LM, "| article-b | 01 |  | `pillar-a`,", "| article-b | 01 |  | `/column/pillar-a`,")]},
    {"name": "事業ページのパスに未公開マーカーを付ける",
     "expect": "コラム以外のパスに注記がある", "edits": [
        (LM, "`article-c`※未公開(コメントアウト), `/ai` | 1 |",
             "`article-c`※未公開(コメントアウト), `/ai`※未公開(コメントアウト) | 1 |")]},
    {"name": "既存記事の末尾注記でマーカーを隠す",
     "expect": "コラム以外のパスに注記がある: pillar-a -> /cases/case-x", "edits": [
        (LM, "| pillar-a | 01 アルファ | ● | `/ai`, `/cases/case-x` |",
             "| pillar-a | 01 アルファ | ● | `/ai`, `/cases/case-x`※未公開(コメントアウト) |")]},
    # --- (cross)注記 ---
    {"name": "カテゴリを跨ぐリンクから(cross)を外す",
     "expect": "カテゴリを跨ぐリンクに(cross)がない", "edits": [
        (LM, "| pillar-d | 02 ベータ | ● | `pillar-a`(cross),", "| pillar-d | 02 ベータ | ● | `pillar-a`,")]},
    {"name": "同一カテゴリのリンクに(cross)を足す",
     "expect": "同一カテゴリのリンクに(cross)がある", "edits": [
        (LM, "| article-c | 01 | ●(第2) | `pillar-a`, `article-b`,",
             "| article-c | 01 | ●(第2) | `pillar-a`, `article-b`(cross),")]},
    # --- 本文側 ---
    {"name": "本文に自己リンクを足す", "expect": "本文に自己リンクがある", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。詳しくは[この記事](/column/article-b/)。")]},
    {"name": "本文で同じコラムへ二重にリンクする",
     "expect": "本文で同じコラムへのリンクが2回ある", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。再掲[記事A](/column/pillar-a/)。")]},
    # --- 宣言文の置き場所とカテゴリ名の正本 ---
    {"name": "第2ピラー宣言を凡例の外へ移す", "expect": "凡例の第2ピラー宣言が0件", "edits": [
        (OL, "- **ピラー**: カテゴリごとのハブ記事(カテゴリ内で最も包括的な1本)。**例外としてカテゴリ01のみ第2ピラー `article-c` を置く**(本番の凡例と同じ書式。checkerはこの宣言文から許可集合を読む)\n",
             "- **ピラー**: カテゴリごとのハブ記事(カテゴリ内で最も包括的な1本)\n"),
        (OL, "## 記事別アウトライン(公開日順)\n",
             "## 付記\n\n**例外としてカテゴリ01のみ第2ピラー `article-c` を置く**\n\n## 記事別アウトライン(公開日順)\n")]},
    {"name": "カテゴリ名をカレンダーと詳細節で同時に改名する",
     "expect": "カテゴリ名が正規語彙と不一致", "edits": [
        (OL, "| pillar-a | 01 アルファ | ● |", "| pillar-a | 01 アルファ改 | ● |"),
        (OL, "カテゴリ: 01 アルファ /", "カテゴリ: 01 アルファ改 /")]},
    {"name": "正規語彙表からカテゴリ名を消す", "expect": "正規語彙表からカテゴリを1件も読めない", "edits": [
        (SG, "| 01 アルファ | アルファ |\n| 02 ベータ | ベータ |\n", "")]},
    # --- 見出しの不在と不正な基準日(tracebackではなくNGで落ちること) ---
    {"name": "セルフチェック結果の見出しを消す",
     "expect": "見出し「## セルフチェック結果」が見つからない", "edits": [
        (LM, "## セルフチェック結果", "## セルフチェック(旧称)")]},
    {"name": "前方参照リンクの見出しを消す",
     "expect": "見出し「## 補足: 前方参照リンク(コメントアウト運用)の一覧」が見つからない", "edits": [
        (LM, "## 補足: 前方参照リンク", "## 付録: 前方参照リンク")]},
    {"name": "凡例の見出しを消す", "expect": "見出し「## 凡例」が見つからない", "edits": [
        (OL, "## 凡例", "## はじめに")]},
    {"name": "基準日に暦として存在しない日付を渡す",
     "expect": "環境変数 LINK_MATRIX_TODAY", "day": "2026-02-30"},
    # --- 本文にしかない内部パス(表→本文の一方向しか見ていないと素通りする) ---
    {"name": "本文にだけ内部パスを足す", "expect": "関係表に未記載のリンク: article-b -> /ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。[G1](/ghost1/)[G2](/ghost2/)[G3](/ghost3/)[G4](/ghost4/)")]},
    {"name": "本文にだけ足したリンクで実本数が上限を超える",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=7本", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。[G1](/ghost1/)[G2](/ghost2/)[G3](/ghost3/)[G4](/ghost4/)")]},
    # --- ルートの実在判定(孤立contentの偽陽性・データ生成ルートの偽陰性) ---
    {"name": "ルートを持たない孤立contentファイルをリンク先にする",
     "expect": "関係表のリンク先パスが実在しない: pillar-a -> /ghost",
     "create": {"content/ghost.md": "# 孤立ファイル\n\nどのルートからも生成されない。\n"},
     "edits": [
        (PA, "(/ai/)", "(/ghost/)"),
        (LM, "| pillar-a | 01 アルファ | ● | `/ai`, `/cases/case-x` |",
             "| pillar-a | 01 アルファ | ● | `/ghost`, `/cases/case-x` |")]},
    {"name": "データ配列にないslugを動的ルートのリンク先にする",
     "expect": "関係表のリンク先パスが実在しない: pillar-a -> /cases/case-y", "edits": [
        (PA, "/cases/case-x/", "/cases/case-y/"),
        (LM, "`/cases/case-x`", "`/cases/case-y`")]},
    # --- 凡例の宣言が実在を指すこと ---
    {"name": "既存記事の宣言行へ未来の記事を足す",
     "expect": "凡例の既存記事宣言が未公開のslugを指す: article-e", "edits": [
        (OL, "- **既存記事**: `pillar-a`", "- **既存記事**: `pillar-a`, `article-e`"),
        (OL, "| 2026-01-05 | 5 |", "| 2026-01-05(公開済) | 5 |"),
        (OL, "- slug: `article-e` / 公開予定日: 2026-01-05 / カテゴリ: 02 ベータ / 事業: `/ai` / ピラー: No / 記事タイプ: 手順 / ステータス: 未着手\n", "")]},
    {"name": "第2ピラー宣言を実在しないカテゴリ・slugへ逃がす(三者同期)",
     "expect": "凡例の第2ピラー宣言が実在しないslugを指す: ghost", "edits": [
        (OL, "**例外としてカテゴリ01のみ第2ピラー `article-c` を置く**",
             "**例外としてカテゴリ99のみ第2ピラー `ghost` を置く**"),
        (OL, "| article-c | 01 アルファ | ●(第2) |", "| article-c | 01 アルファ |  |"),
        (OL, "ピラー: Yes(01・第2ピラー)", "ピラー: No"),
        (LM, "| article-c | 01 | ●(第2) |", "| article-c | 01 |  |"),
        (LM, "| 01 アルファ | pillar-a(4)/article-c(1・第2ピラー) | article-b(1) | ○ |",
             "| 01 アルファ | pillar-a(4) | article-b(1)/article-c(1) | ○ |")]},
    # --- カテゴリ番号・表示名・frontmatter値の正本 ---
    {"name": "正規語彙にないカテゴリ番号へ全体を移す(四者同期)",
     "expect": "正規語彙にないカテゴリ番号: 03", "edits": [
        (LM, "| pillar-d | 02 ベータ |", "| pillar-d | 03 ベータ |"),
        (LM, "| article-e | 02 |", "| article-e | 03 |"),
        (LM, "| 02 ベータ | pillar-d(1) | article-e(1) | ○ |",
             "| 03 ベータ | pillar-d(1) | article-e(1) | ○ |"),
        (OL, "| pillar-d | 02 ベータ |", "| pillar-d | 03 ベータ |"),
        (OL, "| article-e | 02 ベータ |", "| article-e | 03 ベータ |"),
        (OL, "`pillar-d` / 公開予定日: 2026-01-04 / カテゴリ: 02 ベータ",
             "`pillar-d` / 公開予定日: 2026-01-04 / カテゴリ: 03 ベータ"),
        (OL, "`article-e` / 公開予定日: 2026-01-05 / カテゴリ: 02 ベータ",
             "`article-e` / 公開予定日: 2026-01-05 / カテゴリ: 03 ベータ"),
        (OL, "ピラー: Yes(02)", "ピラー: Yes(03)")]},
    {"name": "セルフチェック表のカテゴリ表示名だけ差し替える",
     "expect": "セルフチェック2: カテゴリ名が正規語彙と不一致", "edits": [
        (LM, "| 01 アルファ | pillar-a(4)", "| 01 誤った表示名 | pillar-a(4)")]},
    {"name": "正規語彙表のfrontmatter列を書き換える",
     "expect": "frontmatterの category が正規語彙と不一致", "edits": [
        (SG, "| 01 アルファ | アルファ |", "| 01 アルファ | アルファ改 |")]},
    {"name": "記事のfrontmatterからcategoryを消す",
     "expect": "frontmatterの category が0件ある", "edits": [
        (ART, "category: アルファ\n", "")]},
    # --- リンク抽出の正規化(fragment・コードフェンス・インラインコード) ---
    {"name": "同じ記事へfragment付きで二重にリンクする",
     "expect": "本文で同じコラムへのリンクが2回ある", "edits": [
        (ART, "を参照。事業ページは", "を参照。再掲は[記事A](/column/pillar-a/#section)。事業ページは")]},
    {"name": "本文のリンクをコードフェンスへ退避する",
     "expect": "関係表にあるが本文にないリンク: article-b -> pillar-a", "edits": [
        (ART, "詳しくは[記事A](/column/pillar-a/)を参照。",
              "詳しくは以下。\n\n```markdown\n[記事A](/column/pillar-a/)\n```\n")]},
    {"name": "本文のリンクをインラインコードへ退避する",
     "expect": "関係表にあるが本文にないリンク: article-b -> pillar-a", "edits": [
        (ART, "詳しくは[記事A](/column/pillar-a/)を参照。", "詳しくは `[記事A](/column/pillar-a/)` を参照。")]},
    # --- パスへの(cross)付与と見出しの偽装 ---
    {"name": "事業ページのパスに(cross)を付ける", "expect": "コラム以外のパスに注記がある", "edits": [
        (LM, "| pillar-d | 02 ベータ | ● | `pillar-a`(cross), `article-e`※未公開(コメントアウト), `/ai` |",
             "| pillar-d | 02 ベータ | ● | `pillar-a`(cross), `article-e`※未公開(コメントアウト), `/ai`(cross) |")]},
    {"name": "見出しに接尾辞を足して検査対象を空にする",
     "expect": "見出し「## セルフチェック結果」が見つからない", "edits": [
        (LM, "## セルフチェック結果\n", "## セルフチェック結果(旧)\n")]},
    {"name": "見出しを重複させてどちらが正か分からなくする",
     "expect": "見出し「## 凡例」が2件ある", "edits": [
        (OL, "## 凡例\n", "## 凡例\n\n(重複)\n\n## 凡例\n")]},
    # --- 本文の定義域(frontmatter・コメント・重複・記法) ---
    {"name": "本文のリンクをfrontmatterのdescriptionへ退避する",
     "expect": "関係表にあるが本文にないリンク: article-b -> pillar-a", "edits": [
        (ART, "本文。詳しくは[記事A](/column/pillar-a/)を参照。", "本文。"),
        (ART, 'title: "記事B"', 'title: "記事B"\ndescription: "詳しくは[記事A](/column/pillar-a/)"')]},
    {"name": "設計リンクのパスをコメントアウトへ退避する",
     "expect": "設計リンクのパスがコメントアウトされている: article-b -> /ai", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。", "<!-- 事業ページは[AI活用支援](/ai/)。 -->")]},
    {"name": "表に書いた免除パスをコメントアウトへ退避する",
     "expect": "関係表にあるが本文にないリンク: pillar-a -> /cases/case-x", "edits": [
        (PA, "実績は[事例X](/cases/case-x/)。", "<!-- 実績は[事例X](/cases/case-x/)。 -->")]},
    {"name": "同じ設計リンクを反復して実本数の上限を迂回する",
     "expect": "本文で同じパスへのリンクが5回ある: article-b -> /ai", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。再掲[AI](/ai/)[AI](/ai/)[AI](/ai/)[AI](/ai/)。")]},
    {"name": "参照形式のリンクで本文リンクを増やす",
     "expect": "関係表に未記載のリンク: article-b -> /ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。[G1][g1][G2][g2]\n\n[g1]: /ghost1/\n[g2]: /ghost2/\n")]},
    {"name": "定義のない参照形式をリンクと数えていないか",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=2本",
     "forbid": "/ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。", "定義のない[G1][g1]と `[g1]: /ghost1/` の説明。")]},
    {"name": "参照定義を1〜3スペース字下げしてもリンクとして拾うか",
     "expect": "関係表に未記載のリンク: article-b -> /ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。[G1][g1]\n\n   [g1]: /ghost1/\n")]},
    {"name": "角括弧で囲んだリンク先で本文リンクを増やす",
     "expect": "関係表に未記載のリンク: article-b -> /ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。[G1](</ghost1/>)")]},
    # --- round10レビューの再現(参照定義スコープ・URL解決・属性デコード) ---
    {"name": "コメント内の参照定義で本文のリンク先を差し替える",
     "expect": "関係表に未記載のリンク: article-b -> /ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援][ai]。\n\n[ai]: /ghost1/\n\n<!-- [ai]: /ai/ -->\n")]},
    {"name": "コメント内の参照リンクを本文の定義で解決するか",
     "expect": "関係表に未記載のリンク: article-b -> pillar-d", "edits": [
        (ART, "<!-- [記事C](/column/article-c/) -->",
              "<!-- [記事C](/column/article-c/) [未公開][pd] -->\n\n[pd]: /column/pillar-d/\n")]},
    {"name": "文字参照でhrefのパスを偽装する",
     "expect": "生HTMLの内部リンクがある: article-b -> /ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              '事業ページは[AI活用支援](/ai/)。<a href="&#47;ghost1&#47;">G1</a>')]},
    {"name": "相対パスで書いたリンクを内部リンクとして解決するか",
     "expect": "内部リンクがルート相対でない: article-b -> '../ghost1/'", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。[G1](../ghost1/)")]},
    {"name": "同一オリジンの絶対URLを外部リンク扱いにして逃がさないか",
     "expect": "関係表に未記載のリンク: article-b -> /ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。[G1](https://pineal.co.jp/ghost1/)")]},
    {"name": "GFMのbare URL自動リンクを内部リンクとして拾うか",
     "expect": "関係表に未記載のリンク: article-b -> /ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。詳細は https://pineal.co.jp/ghost1/ を参照。")]},
    {"name": "スキーム相対のホスト表記でルート相対の検査を抜ける",
     "expect": "内部リンクがルート相対でない: article-b -> '//pineal.co.jp/ghost1/'", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。[G1](//pineal.co.jp/ghost1/)")]},
    {"name": "免除パスの生HTMLに絶対URLを置いて表記の検査を抜ける",
     "expect": "内部リンクがルート相対でない: article-b -> 'https://pineal.co.jp/contact/'",
     "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              '事業ページは[AI活用支援](/ai/)。<a href="https://pineal.co.jp/contact/">相談</a>')]},
    {"name": "同じ参照ラベルを2度定義して後の定義で上書きする",
     "expect": "関係表に未記載のリンク: article-b -> /ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。[G1][d]\n\n[d]: /ghost1/\n[d]: /ai/")]},
    {"name": "templateの中身を本文導線として数えていないか",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=2本",
     "forbid": "/ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              '\n\n<template>\n<a href="/ghost1/">下書き</a>\n</template>\n\n')]},
    {"name": "同一ページ内アンカーを内部リンクと誤認しないか",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=2本",
     "forbid": "article-b -> /column/article-b", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。", "[まとめへ](#matome)")]},
    {"name": "data-href属性をhrefと取り違えていないか",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=2本",
     "forbid": "/ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              '<span data-href="/ghost1/">計測用の印</span>')]},
    {"name": "引用符なしのhref属性で本文リンクを増やす",
     "expect": "生HTMLの内部リンクがある: article-b -> /ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。<a href=/ghost1/>G1</a>")]},
    {"name": "コードフェンス内の<!--でフェンス外の-->まで飲み込ませる",
     "expect": "未公開リンクが有効化されている: article-b -> pillar-d", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。\n\n```\n<!-- コメントの書き方\n```\n\n"
              "[未公開記事](/column/pillar-d/)\n\n<!-- ここで閉じる -->\n")]},
    {"name": "生HTMLのアンカーで本文リンクを増やす",
     "expect": "生HTMLの内部リンクがある: article-b -> /ghost1", "edits": [
        (ART, "事業ページは[AI活用支援](/ai/)。",
              '事業ページは[AI活用支援](/ai/)。<a href="/ghost1/">G1</a>')]},
    # --- 実在判定の正本(dist) ---
    {"name": "distにページがないリンク先を関係表に書く",
     "expect": "関係表のリンク先パスが実在しない: article-b -> /ai",
     "delete": [DIST_AI]},
    {"name": "distにディレクトリだけあってページ本体がない",
     "expect": "関係表のリンク先パスが実在しない: pillar-a -> /ghost",
     "create": {"dist/ghost/case-1/index.html": "<!doctype html><title>子だけ</title>\n"},
     "edits": [
        (PA, "(/ai/)", "(/ghost/)"),
        (LM, "| pillar-a | 01 アルファ | ● | `/ai`, `/cases/case-x` |",
             "| pillar-a | 01 アルファ | ● | `/ghost`, `/cases/case-x` |")]},
    {"name": "distがないまま検査を通そうとする",
     "expect": "dist がない", "rmtree": ["dist"]},
    {"name": "ソースにだけ存在するルートで実在を偽装する",
     "expect": "関係表のリンク先パスが実在しない: pillar-a -> /cases/case-y", "edits": [
        (PA, "/cases/case-x/", "/cases/case-y/"),
        (LM, "`/cases/case-x`", "`/cases/case-y`"),
        ("src/data/cases.ts", "];", "  { slug: 'case-y', title: '事例Y' },\n];")]},
    # --- 孤立記事(被リンク0)は表と実測が一致していても通さない ---
    {"name": "被リンク0の記事を表ぐるみで整合させる",
     "expect": "被リンクが0本の記事がある: article-b", "edits": [
        (ARTC, "[記事B](/column/article-b/)", "[事例X](/cases/case-x/)"),
        (LM, "| article-c | 01 | ●(第2) | `pillar-a`, `article-b`, `/ai` | 1 |",
             "| article-c | 01 | ●(第2) | `pillar-a`, `/cases/case-x`, `/ai` | 1 |"),
        (LM, "`article-c`※未公開(コメントアウト), `/ai` | 1 |",
             "`article-c`※未公開(コメントアウト), `/ai` | 0 |"),
        (LM, "最小は1で、該当は4記事(`article-b`, `article-c`, `article-e`, `pillar-d`)",
             "最小は0で、該当は1記事(`article-b`)"),
        (LM, "| 01 アルファ | pillar-a(4)/article-c(1・第2ピラー) | article-b(1) | ○ |",
             "| 01 アルファ | pillar-a(4)/article-c(1・第2ピラー) | article-b(0) | ○ |")]},
    # --- docs側のコード/コメントの解釈順(コードが先、コメントが後) ---
    {"name": "コードフェンス内の`<!--`でdocsの行を隠す",
     "expect": "被リンク数の不一致: pillar-a 表=3 実測=4", "edits": [
        (LM, "| pillar-a | 01 アルファ | ● | `/ai`, `/cases/case-x` | 4 |",
             "```\n<!-- コメントの書き方\n```\n| pillar-a | 01 アルファ | ● | `/ai`, `/cases/case-x` | 3 |\n"
             "<!-- ここまで -->")]},
    {"name": "4スペース字下げの```でdocsの行を隠す",
     "expect": "被リンク数の不一致: pillar-a 表=3 実測=4", "edits": [
        (LM, "| pillar-a | 01 アルファ | ● | `/ai`, `/cases/case-x` | 4 |",
             "    ```\n| pillar-a | 01 アルファ | ● | `/ai`, `/cases/case-x` | 3 |\n    ```")]},
    # --- 正規語彙の一意性 ---
    {"name": "2カテゴリのfrontmatter値を同じ値にする(三者同期)",
     "expect": "正規語彙表のfrontmatter値が重複", "edits": [
        (SG, "| 02 ベータ | ベータ |", "| 02 ベータ | アルファ |"),
        (PD, "category: ベータ", "category: アルファ"),
        ("content/column/article-e.md", "category: ベータ", "category: アルファ")]},
    # --- コードブロックの記法(tilde・複数バッククォート・字下げ) ---
    {"name": "tildeフェンス内のリンク例を実リンクと数えていないか",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=2本", "edits": [
        (ART, "本文。詳しくは[記事A](/column/pillar-a/)を参照。",
              "本文。\n\n~~~markdown\n[記事A](/column/pillar-a/)\n~~~\n")]},
    {"name": "ダブルバッククォート内のリンク例を実リンクと数えていないか",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=2本", "edits": [
        (ART, "本文。詳しくは[記事A](/column/pillar-a/)を参照。",
              "本文。書き方は ``[記事A](/column/pillar-a/)`` のとおり。")]},
    {"name": "4スペース字下げコード内のリンク例を実リンクと数えていないか",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=2本", "edits": [
        (ART, "本文。詳しくは[記事A](/column/pillar-a/)を参照。",
              "本文。\n\n    [記事A](/column/pillar-a/)\n")]},
    {"name": "4バッククォートのフェンス内のリンク例を実リンクと数えていないか",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=2本",
     "forbid": "/ghost1", "edits": [
        (ART, "本文。詳しくは[記事A](/column/pillar-a/)を参照。",
              "本文。\n\n````markdown\n```\n[G1](/ghost1/)\n```\n````\n")]},
    {"name": "閉じフェンスに情報文字列を付けても閉じたと誤認しないか",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=2本",
     "forbid": "/ghost1", "edits": [
        (ART, "本文。詳しくは[記事A](/column/pillar-a/)を参照。",
              "本文。\n\n```markdown\n[記事A](/column/pillar-a/)\n``` js\n[G1](/ghost1/)\n```\n")]},
    # 閉じないフェンスは文末までコード。以降の実リンクも消えるので本数は0本になる
    {"name": "閉じないフェンスのまま本文が終わってもコードとして扱うか",
     "expect": "関係表にあるが本文にないリンク: article-b -> /ai",
     "forbid": "/ghost1", "edits": [
        (ART, "本文。詳しくは[記事A](/column/pillar-a/)を参照。",
              "本文。\n\n```markdown\n[記事A](/column/pillar-a/)\n[G1](/ghost1/)\n")]},
    {"name": "リスト内の8スペース字下げコードのリンク例を実リンクと数えていないか",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=2本",
     "forbid": "/ghost1", "edits": [
        (ART, "本文。詳しくは[記事A](/column/pillar-a/)を参照。",
              "本文。\n\n- 書き方の例\n\n        [記事A](/column/pillar-a/)\n        [G1](/ghost1/)\n")]},
    {"name": "コードブロック内のコメントをコメントアウト運用と数えていないか",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=2本",
     "forbid": "pillar-d", "edits": [
        (ART, "本文。詳しくは[記事A](/column/pillar-a/)を参照。",
              "本文。\n\n```markdown\n<!-- [未公開記事](/column/pillar-d/) -->\n```\n")]},
    {"name": "docsのコードブロック内の見出しを重複扱いしていないか",
     "expect": "関係表に未記載のリンク: article-b -> /ghost1",
     "forbid": "見出し「## セルフチェック結果」が2件ある", "edits": [
        (LM, "## リンク関係表", "```markdown\n## セルフチェック結果\n```\n\n## リンク関係表"),
        (ART, "事業ページは[AI活用支援](/ai/)。",
              "事業ページは[AI活用支援](/ai/)。[G1](/ghost1/)")]},
    # --- 外部URLとトップページ ---
    {"name": "スキーム相対の外部URLを内部リンク扱いしていないか",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=2本", "edits": [
        (ART, "本文。詳しくは[記事A](/column/pillar-a/)を参照。",
              "本文。出典は[CDN](//cdn.example.com/foo)。")]},
    {"name": "トップページへのリンクを表に書けず偽NGにしていないか",
     "expect": "本文の実リンク数が3〜5本の範囲外: article-b=2本", "edits": [
        (ART, "本文。詳しくは[記事A](/column/pillar-a/)を参照。", "本文。[トップ](/)を参照。")]},
    # --- 詳細節の置き場所 ---
    {"name": "詳細節の行を別の節へ移す",
     "expect": "公開カレンダーにあるが詳細節にないslug: article-b", "edits": [
        (OL, "- slug: `article-b` / 公開予定日: 2026-01-02 / カテゴリ: 01 アルファ / 事業: `/ai` / ピラー: No / 記事タイプ: 解説 / ステータス: レビュー済み\n", ""),
        (OL, "## 記事別アウトライン(公開日順)\n",
             "## 付録\n\n- slug: `article-b` / 公開予定日: 2026-01-02 / カテゴリ: 01 アルファ / 事業: `/ai` / ピラー: No / 記事タイプ: 解説 / ステータス: レビュー済み\n\n## 記事別アウトライン(公開日順)\n")]},
]

def run(root, day):
    # PATH はそのまま渡す。checker が node(リンク抽出)を起動するので、切り詰めると
    # 「抽出に失敗したせいで全部NG」という無意味な赤になる
    env = {
        "LINK_MATRIX_ROOT": str(root),
        "LINK_MATRIX_TODAY": day,
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    return subprocess.run([sys.executable, str(CHECKER)], capture_output=True, text=True, env=env)


def apply(work, mutation):
    """変異を適用する。対象文字列が見つからなければ理由を返す。"""
    for rel, old, new in mutation.get("edits", []):
        path = work / rel
        text = path.read_text(encoding="utf-8")
        if old not in text:
            return f"変異の対象文字列が見つからない: {old[:60]}"
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    for rel in mutation.get("delete", []):
        path = work / rel
        if not path.exists():
            return f"削除対象が存在しない: {rel}"
        path.unlink()
    for rel in mutation.get("rmtree", []):
        path = work / rel
        if not path.is_dir():
            return f"削除対象のディレクトリが存在しない: {rel}"
        shutil.rmtree(path)
    for rel, content in mutation.get("create", {}).items():
        path = work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for rel, dest in mutation.get("rename", {}).items():
        path = work / rel
        if not path.exists():
            return f"改名対象が存在しない: {rel}"
        path.rename(work / dest)
    return None


def main():
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td) / "base"
        shutil.copytree(FIXTURE, base)
        baseline = run(base, BASE_TODAY)
        if baseline.returncode != 0:
            print("FAIL 変異なしのfixtureで違反が出ている。checkerかfixtureを直すこと。")
            print(baseline.stdout)
            return 1
        print(f"OK   [変異なし] exit=0 — {baseline.stdout.strip().splitlines()[-1]}")

        missed = 0
        for mutation in MUTATIONS:
            name = mutation["name"]
            work = pathlib.Path(td) / "work"
            shutil.rmtree(work, ignore_errors=True)
            shutil.copytree(base, work)
            problem = apply(work, mutation)
            if problem:
                print(f"FAIL [{name}] {problem}")
                missed += 1
                continue
            result = run(work, mutation.get("day", BASE_TODAY))
            if result.stderr.strip():
                # 例外で落ちても exit 1 になる。検出と区別がつかないので落とす
                print(f"FAIL [{name}] checkerが例外で終了した: {result.stderr.strip().splitlines()[-1]}")
                missed += 1
                continue
            ng = [line[3:] for line in result.stdout.splitlines() if line.startswith("NG ")]
            hit = [line for line in ng if mutation["expect"] in line]
            # forbid は「この変異で出てはいけない偽NG」。狙った検出と同時に確かめる
            forbid = mutation.get("forbid")
            false_ng = [line for line in ng if forbid and forbid in line]
            if false_ng:
                print(f"MISS [{name}] 出てはいけないNGが出た: {false_ng[0][:90]}")
                missed += 1
            elif result.returncode == 1 and hit:
                print(f"OK   [{name}] 検出{len(ng)}件 — {hit[0][:90]}")
            elif result.returncode == 1:
                print(f"MISS [{name}] NG{len(ng)}件は出たが期待の断片がない: {mutation['expect']!r}")
                for line in ng[:3]:
                    print(f"       実際: {line[:90]}")
                missed += 1
            else:
                print(f"MISS [{name}] exit={result.returncode} 検出={len(ng)}")
                missed += 1

    print(f"\nミューテーションテスト: {len(MUTATIONS)}変異中 取りこぼし {missed}件")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
