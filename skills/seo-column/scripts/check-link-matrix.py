#!/usr/bin/env python3
"""link-matrix.md と記事本文・outline.md の内部リンク設計が一致しているかを検査する。

link-matrix.md は週次リンクパッチの判断材料になる正本だが、記事側にリンクを
足しても手で表を更新し忘れると静かにズレる。2026-08-15のPR #213レビューで
実ソースにある12件の参照が表から欠落していたのが実例(うち7件はコメントアウト
参照で、前方参照一覧からも漏れていた)。以下を不変条件として固定する。

  1. 記事本文の内部リンクが「リンク関係表」と双方向に一致すること
     (コラム記事は全件、それ以外の内部パスは下記の「本数外」を除く全件)
  2. 「※未公開(コメントアウト)」マーカーが本文のコメント状態と一致すること
  3. 「被リンク数」列が関係表から数え直した入次数と一致し、被リンク0の記事がないこと
  4. 未公開マーカー付きペアと「前方参照リンク一覧」が双方向に一致すること
  5. 前方参照一覧の日付(リンク元・リンク先とも)が outline.md の公開日と一致すること
  6. 公開日が追いついた前方参照が残っていないこと(週次リンクパッチの取りこぼし)
  7. セルフチェック結果の被リンク数・最小件数リスト・判定列が実測と一致すること
  8. 関係表・セルフチェック表に重複がないこと
  9. outline.md の公開カレンダーと詳細節が双方向に一致すること
 10. カテゴリとピラー指定が link-matrix.md と outline.md の両方で一致すること
 11. 記事集合が計画と一致すること(公開日到来済みの記事は実ファイルがあり、
     実ファイルは必ず関係表とカレンダーに行を持つ)
 12. ピラーがカテゴリごとにちょうど1本で、第2ピラーは outline.md の凡例が
     宣言した1組だけであること。宣言は実在のカテゴリ・実在のslugを指すこと
 13. 「本文リンク先」列が書式どおりで、内部パスが実在ページを指し、
     執筆済み記事では表に書いたリンクが本文にも実在すること
 14. 未公開マーカーの要否が表の全行で公開日から決まること(未執筆行も対象)
 15. 「(cross)」注記がリンク元とリンク先のカテゴリ差と一致すること
 16. カテゴリ番号・カテゴリ名・frontmatter の category が style-guide.md の
     正規語彙表(両列)と一致し、どちらの列にも重複がないこと
 17. 凡例の「既存記事」宣言が実在・公開済みのslugだけを指すこと

「本文リンク先」列のセルは `slug` または `/path` を並べたもの。**`(cross)` と
`※未公開(コメントアウト)` を付けられるのは slug だけで、`/path` にはどちらも
付けられない**(パスは公開日もカテゴリも持たないため)。コラム記事は必ず bare slug
で書く(`/column/xxx` のパス表記を許すと被リンク・前方参照の検査を迂回できる)。

内部パスの分類:
  - **設計リンク**(`/ai` `/marketing-creative` `/cases` など): 関係表と本文で
    双方向に一致させ、実在も確認し、§5の「本文中リンク3〜5本」に数える
  - **本数外**(`/contact`、実績記事 `/topics/*` `/cases/*`、図版などの拡張子付き):
    CTA導線と出典リンクなので本数に数えない。表に書いた場合は実在と本文への
    存在だけ確認する

リンク先の実在は **dist(ビルド成果物)だけ**で照合する。ソースから推定すると
「動的ルートのファイル名が実URLの形か」「データ配列に本当にその要素があるか」を
当てにいくことになり、必ず穴が残る。dist がなければ実在判定をせずその旨をNGにする。

本文のリンク抽出は `scripts/extract-column-links.mjs` に委譲する。mdast(GFM)と
parse5 で解釈するので、フェンスの長さ・閉じフェンスの情報文字列・リスト内の字下げ
コード・角括弧付きリンク先 `[x](</ai/>)`・参照形式・引用符なしの生HTML属性・
文字参照といった境界が、実際のレンダリングと同じ解釈になる。URLは記事URLを base に
解決し、同一オリジンだけを内部リンクとして受け取る(`../ai/` や
`https://pineal.co.jp/ai/` を外部扱いにすると、そのまま検査の外に置ける)。
ただし表記は `/path/` のルート相対だけを許す。

生HTMLの `<a href="/…">` は、設計リンクに使うことだけを禁止する(DLカードの画像と
配布ファイルは本数外なので生HTMLのままでよい)。同じ設計リンクの反復も禁止する
(集合にすると本数の上限を反復で迂回できる)。設計リンクのコメントアウトも許さない
(パスは公開日を持たないので、隠したまま本数を満たす手段になる)。免除パスも
コメント内だけにあるものは「本文にある」と数えない。

1・2・6は content/column/ に実ファイルがある記事のみを対象にする(未執筆記事は
表が計画値として先行するため)。それ以外は表全体を対象にする。未執筆行のマーカーは
14が公開日から直接決めるので、表と前方参照一覧を同時に壊しても整合しない。

使い方: python3 scripts/check-link-matrix.py
違反があれば一覧を出して exit 1。

テスト用に環境変数 LINK_MATRIX_ROOT(検査対象のルート)と LINK_MATRIX_TODAY
(検査6の基準日、YYYY-MM-DD)で差し替えできる。本番のCIでは設定しない。
"""
import collections
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys

from seo_column_lib import DocsError, find_section, load_categories, strip_blocks, visible

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("LINK_MATRIX_ROOT") or HERE.parent)
EXTRACTOR = HERE / "extract-column-links.mjs"
COLUMN_PREFIX = "/column/"
SLUG_RE = r"`([a-z0-9-]+)`"
MARKER = "※未公開(コメントアウト)"
# リンクカード(<!-- link-card: slug -->)は本文中の生リンクの直後に置く運用。
# マーカー自体にはMarkdownリンク記法が無いため extract-column-links.mjs では
# 抽出されない(live/commented/anchorsのいずれにも入らない)。したがって
# 重複リンク数のカウント対象には含めない(表と本文の突合・被リンク数の両方で
# 二重計上しない)。その代わりここでは「カードの対象は既に本文の生リンクに
# ある」ことだけを確認する(生リンクを書かずカードだけを置く運用の逃げ道を塞ぐ)。
LINK_CARD_MARKER = re.compile(r"^<!--\s*link-card:\s*([a-z0-9-]+)\s*-->$", re.M)
# パスの許容文字は実ルートに合わせる(content/topics には AI_event.md のような大文字・
# アンダースコア混じりのファイルが実在する)
PATH_CHARS = r"[A-Za-z0-9_-]"
# 記事slugは bare で書く。`/column/xxx` のパス表記を許すとコラム間リンクが
# パス扱いになり、被リンク数・前方参照・重複の検査をまるごと迂回できる。
# (cross)・マーカーは slug 側にしか置けない
SEGMENT_RE = re.compile(
    r"^`(?:"
    r"(?P<slug>[a-z0-9-]+)`"
    r"(?P<cross>\(cross\))?"
    r"(?P<marker>※未公開\(コメントアウト\))?"
    r"|"
    rf"(?P<path>/(?!column(?:/|$)){PATH_CHARS}+(?:/{PATH_CHARS}+)*)`"
    r"(?P<path_extra>.*)"
    r")$"
)
JST = datetime.timezone(datetime.timedelta(hours=9))
PILLAR_VALUES = ("", "●", "●(第2)")
LINKS_PER_ARTICLE = (3, 5)  # style-guide.md §5「本文中リンクは3〜5本」
# §5の本数に数えない経路。トップ・CTA導線と、実績記事への出典リンク。ここに載らない
# 内部パスはすべて関係表と双方向に一致させ、実在も確認する
EXEMPT_PATHS = ("/", "/contact")
EXEMPT_PREFIXES = ("/topics/", "/cases/", "/images/", "/download/", "/recruit/")
# 技術記事シリーズ(「AI業務標準書」実装記録。category: AI駆動開発)は、キーワードマップ
# 由来の50本SEOプラン(outline.mdの公開カレンダー・本ファイルのリンク関係表)の対象外。
# 内部リンクとスケジュールは docs/seo-column/outline.md 末尾の別表、本ファイル末尾の
# 別セクションで管理し、このスクリプトの50本不変条件(written == rows == plan)からは
# 除外する。50本プランに合流させる場合はここから外し、通常の行として登録すること
NON_SEO_SLUGS = {
    "inhouse-ai-agent-brain",
    "meeting-minutes-ai-agent-pipeline",
    "proposal-draft-ai-agent",
    "morning-information-collector-agent",
    "silent-failure-monitoring",
    "context-window-compaction",
    "knowledge-placement-retrieval",
    "skill-subagent-work-decomposition",
    "agent-delegation-levels",
    "fde-agent-platform-work",
}

H_MATRIX = "## リンク関係表"
H_SELFCHECK = "## セルフチェック結果"
H_FORWARD = "## 補足: 前方参照リンク(コメントアウト運用)の一覧"
H_LEGEND = "## 凡例"
H_DETAIL = "## 記事別アウトライン(公開日順)"


def today(bad):
    override = os.environ.get("LINK_MATRIX_TODAY")
    if override:
        return parse_date(override, "環境変数 LINK_MATRIX_TODAY", bad)
    return datetime.datetime.now(JST).date()


def docs_text(relative):
    """docs のMarkdownを、コードブロックとコメントを落とした形で読む。

    順序が肝。コードを先に落とす。逆にすると、フェンスの中に書いた `<!--` が
    フェンス外の `-->` まで飲み込み、その区間の表や見出しが検査から消える。
    """
    return visible(strip_blocks((ROOT / relative).read_text(encoding="utf-8")))


def parse_date(value, label, bad):
    """暦として不正な日付(2026-02-30 等)でtracebackにせずNGへ落とす。"""
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        bad.append(f"{label}: 日付として解釈できない: {value!r}")
        return None


def section(text, heading, label, bad):
    """節の切り出し(seo_column_lib)。読めなければNGに落として None を返す。"""
    try:
        return find_section(text, heading)
    except DocsError as e:
        bad.append(f"{label}: {e}")
        return None


def exempt_path(path):
    """§5の本数に数えない内部パスか(CTA導線・実績記事の出典・アセット)。"""
    return (
        path in EXEMPT_PATHS
        or path.startswith(EXEMPT_PREFIXES)
        or "." in path.rsplit("/", 1)[-1]
    )


def path_exists(path):
    """`/ai` `/cases/xxx` のような内部パスが実在ページか。

    **判定は dist(ビルド成果物)だけを正本にする。** ソースから推定しようとすると
    「動的ルートのファイル名が実URLの形か」「データ配列に本当にその要素があるか」を
    TypeScriptを読まずに当てることになり、テンプレートリテラルの中の文字列を実要素と
    誤認するような穴が必ず残る。実際に生成されたページを見れば当てずっぽうは要らない。
    CIもこのcheckerをビルドの後に走らせる(dist_missing() が先に不足を知らせる)。
    """
    rel = path.strip("/")
    if not rel:
        return True
    if "." in rel.rsplit("/", 1)[-1]:
        # 図版などのアセット。正本は content/images/ で、public/ は生成コピー
        return any(
            (ROOT / base / rel).is_file() for base in ("content", "public", "dist")
        )
    dist = ROOT / "dist"
    return (dist / rel / "index.html").is_file() or (dist / f"{rel}.html").is_file()


def dist_missing():
    """dist がなければ実在判定ができない。黙って全部NGにせず理由を1件で返す。"""
    if (ROOT / "dist").is_dir():
        return None
    return "dist がない。リンク先の実在は生成物で確かめるので、先に npm run build を実行する"


def read_categories(bad):
    """style-guide.md の正規語彙表を読む(正本の解釈は seo_column_lib と共有する)。

    第2列は check-column.py が frontmatter の検査に使う正本でもある。読み方が
    2箇所に分かれていると、片方だけが重複を見逃す形でズレる。
    """
    try:
        return load_categories(ROOT)
    except DocsError as e:
        bad.append(f"style-guide: {e}")
        return {}


def split_category(value, names, label, bad):
    """`11` / `11 AIマーケ戦略・事例` を番号へ正規化し、正規語彙と照合する。"""
    m = re.fullmatch(r"(\d{2})(?: (.+))?", value.strip())
    if not m:
        bad.append(f"{label}: カテゴリ表記が不正: {value.strip()!r}(「NN」または「NN 名前」)")
        return value.strip()
    num, name = m.group(1), m.group(2)
    if names and num not in names:
        # 番号だけの表記でも正本にないカテゴリは通さない。番号を移すだけで
        # 名前の照合をまるごと迂回できてしまう
        bad.append(f"{label}: style-guide の正規語彙にないカテゴリ番号: {num}")
    elif name and names and names[num][0] != name:
        bad.append(
            f"{label}: カテゴリ名が正規語彙と不一致: {num} {name!r} "
            f"正本={names[num][0]!r}"
        )
    return num


def extract_links(bad):
    """CommonMarkの構文木からリンクを取る(scripts/extract-column-links.mjs)。

    正規表現でMarkdownを解釈するとフェンスや生HTMLの境界を必ず取り違える。
    パーサに解釈させれば、検査の判断が実際のレンダリング結果と一致する。
    """
    env = dict(os.environ, LINK_MATRIX_ROOT=str(ROOT))
    try:
        proc = subprocess.run(
            ["node", str(EXTRACTOR)], capture_output=True, text=True, env=env, check=False
        )
    except OSError as e:
        bad.append(f"リンク抽出({EXTRACTOR.name})を起動できない: {e}")
        return {}
    if proc.returncode != 0:
        bad.append(f"リンク抽出({EXTRACTOR.name})が失敗: {proc.stderr.strip()[:300]}")
        return {}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        bad.append(f"リンク抽出({EXTRACTOR.name})の出力を読めない: {e}")
        return {}
    # 契約が崩れたらtracebackではなくNGで落とす。抽出側を書き換えたときに
    # 「例外で異常終了 = 何も検査していない」状態を見逃さないため
    if not isinstance(data, dict):
        bad.append(f"リンク抽出({EXTRACTOR.name})の出力が辞書ではない")
        return {}
    for slug, entry in sorted(data.items()):
        if not isinstance(entry, dict) or set(entry) != {"live", "commented", "anchors"}:
            bad.append(f"リンク抽出の出力形式が不正: {slug}(live/commented/anchors を持つ辞書)")
            return {}
        for key, items in sorted(entry.items()):
            if not isinstance(items, list) or not all(
                isinstance(x, dict)
                and isinstance(x.get("raw"), str)
                and (x.get("path") is None or isinstance(x.get("path"), str))
                for x in items
            ):
                bad.append(f"リンク抽出の出力形式が不正: {slug}.{key}({{raw, path}} の配列)")
                return {}
    return data


def read_articles(bad):
    """記事本文のリンクをコメント内/外に分け、frontmatterの公開日・カテゴリも返す。"""
    commented, live, published, categories = set(), set(), {}, {}
    body_paths, body_exempt = {}, {}
    extracted = extract_links(bad)
    for path in sorted((ROOT / "content/column").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        # frontmatterは先頭の --- ブロックだけを見る(本文に同名行を置いても効かない)
        fm = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", text, flags=re.S)
        if not fm:
            bad.append(f"先頭に frontmatter ブロック(---)がない: {path.name}")
        else:
            values = re.findall(r"^publishedDate:[ \t]*(.*?)[ \t]*$", fm.group(1), flags=re.M)
            if len(values) != 1:
                bad.append(f"frontmatterの publishedDate が{len(values)}件ある: {path.name}")
            else:
                raw = values[0].strip("'\"")
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                    bad.append(
                        f"frontmatterの publishedDate が YYYY-MM-DD ではない: {path.name}={values[0]!r}"
                    )
                else:
                    date = parse_date(raw, f"frontmatter({path.name})", bad)
                    if date:
                        published[path.stem] = date
            cats = re.findall(r"^category:[ \t]*(.*?)[ \t]*$", fm.group(1), flags=re.M)
            if len(cats) != 1:
                bad.append(f"frontmatterの category が{len(cats)}件ある: {path.name}")
            else:
                categories[path.stem] = cats[0].strip("'\"")
        found = extracted.get(path.stem)
        if found is None:
            bad.append(f"リンク抽出の結果に記事がない: {path.stem}")
            found = {"live": [], "commented": [], "anchors": []}
        def check_raw(items, label):
            # 内部リンクはルート相対だけを許す。同一ホストの絶対URLや `../` や
            # `//host/path` は実際には内部導線なので抽出はするが、表記が揺れると
            # 表との照合も引っ越し時の一括置換も当てにならなくなる
            for link in items:
                if not link["path"]:
                    continue
                raw = link["raw"]
                if not raw.startswith("/") or raw.startswith("//"):
                    bad.append(
                        f"内部リンクがルート相対でない: {path.stem} -> {raw!r}"
                        f"({label}。`/path/` の形で書く)"
                    )

        # 生HTMLの <a href> はMarkdown記法と混ぜて数えると表との照合が成り立たない。
        # 設計リンクに使うことだけを禁止して抜け道を塞ぐ
        # (DLカードの画像・配布ファイルは本数外なので生HTMLのままでよい)
        check_raw(found["anchors"], "生HTML")
        for link in found["anchors"]:
            target = link["path"]
            if target and not exempt_path(target):
                bad.append(
                    f"生HTMLの内部リンクがある: {path.stem} -> {target}"
                    "(設計リンクは `[表示](/path)` のインライン記法で書く)"
                )

        def links(items, label):
            check_raw(items, label)
            found = [link["path"] for link in items if link["path"]]
            slugs = [p[len(COLUMN_PREFIX):] for p in found if p.startswith(COLUMN_PREFIX)]
            paths = collections.Counter(p for p in found if not p.startswith(COLUMN_PREFIX))
            for slug, count in sorted(collections.Counter(slugs).items()):
                # コラム間リンクは関係表が1本として持つので、本文の重複は表と数が合わなくなる
                if count > 1:
                    bad.append(f"本文で同じコラムへのリンクが{count}回ある: {path.stem} -> {slug}({label})")
            for target, count in sorted(paths.items()):
                # 設計リンクも表は1本として持つ。同じパスの反復で3〜5本の上限を
                # 迂回できないよう、コラムと同じく重複を禁じる
                if count > 1 and not exempt_path(target):
                    bad.append(f"本文で同じパスへのリンクが{count}回ある: {path.stem} -> {target}({label})")
            if path.stem in slugs:
                bad.append(f"本文に自己リンクがある: {path.stem} -> {path.stem}({label})")
            return set(slugs) - {path.stem}, set(paths)

        live_targets, live_paths = links(found["live"], "本文")
        commented_targets, commented_paths = links(found["commented"], "コメント内")
        # リンクカードは重複リンク数のカウント対象に含めない(下のコメント参照)。
        # ここでは「マーカーの対象は既に本文の生リンクとして存在する」ことだけ確認する。
        for card_target in LINK_CARD_MARKER.findall(text):
            if card_target == path.stem:
                bad.append(f"リンクカードが自己参照している: {path.stem} -> {card_target}")
            elif card_target not in live_targets:
                bad.append(
                    f"リンクカードの対象が本文リンクと一致しない: {path.stem} -> {card_target}"
                    "(先に生リンクを本文に書く)"
                )
        for target in sorted(live_targets & commented_targets):
            bad.append(
                f"本文で有効リンクとコメントアウトが重複: {path.stem} -> {target}"
                "(どちらが正か判断できないため片方を消す)"
            )
        live |= {(path.stem, t) for t in live_targets}
        commented |= {(path.stem, t) for t in commented_targets - live_targets}
        # 内部パスは公開日を持たないのでコメントアウト運用の対象外。コメントの中に
        # 置いたものは画面に出ないので「本文にある」と数えない(設計リンクを隠したまま
        # 3〜5本を満たせてしまう)
        for target in sorted(commented_paths - live_paths):
            if not exempt_path(target):
                bad.append(
                    f"設計リンクのパスがコメントアウトされている: {path.stem} -> {target}"
                    "(パスは公開日を持たないのでコメントアウト運用の対象外)"
                )
        # 免除パスも「表に書いてある＝本文にある」を保つ。コメント内だけのものを
        # 本文扱いにすると、表に載せた導線を隠したまま検査を通せる
        body_paths[path.stem] = {p for p in live_paths if not exempt_path(p)}
        body_exempt[path.stem] = {p for p in live_paths if exempt_path(p)}
        # 生HTMLの免除パス(DLカードの画像・配布ファイル)も表に書いた分は本文にある
        body_exempt[path.stem] |= {
            link["path"] for link in found["anchors"]
            if link["path"] and exempt_path(link["path"])
        }
    return commented, live, published, categories, body_paths, body_exempt


def read_matrix(bad, legacy, names):
    """リンク関係表を {slug: {"cells", "targets", "paths", "links", ...}} で返す。"""
    # コードブロックの中の見出しやテーブル例を実データと数えない(重複見出し扱いで
    # 検査対象を空にできてしまう)
    text = docs_text("docs/seo-column/link-matrix.md")
    table = section(text, H_MATRIX, "link-matrix", bad)
    if table is None:
        return text, {}
    rows = {}
    for line in table.splitlines():
        if not line.startswith("| ") or line.startswith("| slug"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        slug = cells[0].strip("`")
        cell = cells[3]
        if slug in legacy:
            # 既存記事の行は「リンク先は現状のまま」の注記を末尾に持つ
            # 直前に空白がある末尾注記だけを落とす。空白なしで詰めると
            # `/ai`※未公開(コメントアウト) のマーカーまで食ってしまう
            cell = re.sub(r"\s+\([^`)]*\)\s*$", "", cell)
        targets, paths, exempt = {}, set(), set()
        segments = [seg.strip() for seg in cell.split(",") if seg.strip()]
        for seg in segments:
            m = SEGMENT_RE.match(seg)
            if not m:
                bad.append(
                    f"本文リンク先セルの書式が不正: {slug} の {seg!r}"
                    "(`slug` に (cross) と ※未公開(コメントアウト) / `/path` は装飾なし)"
                )
                continue
            if m.group("path"):
                target = m.group("path")
                if m.group("path_extra"):
                    # 事業・事例ページは公開日もカテゴリも持たないので、マーカーも
                    # (cross)も意味を持たない。許すと検査4・6・15のどの網にもかからない
                    bad.append(
                        f"関係表でコラム以外のパスに注記がある: {slug} -> {target}"
                        f"{m.group('path_extra')!r}(パスには (cross) もマーカーも付けられない)"
                    )
                if target in paths | exempt:
                    bad.append(f"関係表の行内でリンク先が重複: {slug} -> {target}")
                if not path_exists(target):
                    bad.append(f"関係表のリンク先パスが実在しない: {slug} -> {target}")
                (exempt if exempt_path(target) else paths).add(target)
                continue
            target = m.group("slug")
            if target == slug:
                bad.append(f"関係表に自己リンクがある: {slug} -> {target}")
            if target in targets:
                bad.append(f"関係表の行内でリンク先が重複: {slug} -> {target}")
            targets[target] = seg
        if slug in rows:
            bad.append(f"関係表に重複行: {slug}")
        if cells[2] not in PILLAR_VALUES:
            bad.append(f"関係表のピラー列が不正: {slug}={cells[2]!r}(許容: 空 / ● / ●(第2))")
        rows[slug] = {
            "cells": cells,
            "targets": targets,
            "paths": paths,
            "exempt": exempt,
            "links": len(targets) + len(paths),
            "category": split_category(cells[1], names, f"関係表({slug})", bad),
            "pillar": cells[2],
        }
    return text, rows


def read_forward(text, bad):
    """前方参照一覧の {(source, target): (表記されたsource日, target日)} を返す。"""
    body = section(text, H_FORWARD, "link-matrix", bad)
    if body is None:
        return {}
    pairs = {}
    for line in body.splitlines():
        m = re.match(r"- `([a-z0-9-]+)`\((\d{2}-\d{2})\)", line)
        if not m or "→" not in line:
            continue
        source, source_date = m.group(1), m.group(2)
        tail = line.split("→", 1)[1].split("※")[0]
        for target, date in re.findall(r"`([a-z0-9-]+)`\((\d{2}-\d{2})\)", tail):
            if (source, target) in pairs:
                bad.append(f"前方参照一覧に重複: {source} -> {target}")
            pairs[(source, target)] = (source_date, date)
    return pairs


def read_plan(bad, names):
    """outline.md から (plan, 第2ピラー, 既存記事) を返す。

    公開カレンダー(全50行)を正本とし、詳細節と双方向に突き合わせる。
    第2ピラーと既存記事の許可集合は凡例の宣言文から読む(checkerに焼き込まない)。
    """
    text = docs_text("docs/seo-column/outline.md")
    # 宣言文は凡例の節に置く。全文検索にすると、末尾の雑記に書いた宣言でも
    # 例外が通ってしまい「凡例が正本」という運用が崩れる
    legend = section(text, H_LEGEND, "outline", bad) or ""
    declared = re.findall(r"例外としてカテゴリ(\d{2})のみ第2ピラー\s*`([a-z0-9-]+)`", legend)
    if len(declared) != 1:
        bad.append(
            f"outline: 凡例の第2ピラー宣言が{len(declared)}件"
            "(「例外としてカテゴリNNのみ第2ピラー `slug`」を凡例にちょうど1件書く)"
        )
    second_pillar = declared[0] if len(declared) == 1 else None
    legacy_lines = [line for line in legend.splitlines() if "**既存記事**:" in line]
    if len(legacy_lines) != 1:
        bad.append(
            f"outline: 凡例の既存記事宣言が{len(legacy_lines)}件"
            "(「**既存記事**: `slug`」を凡例にちょうど1件書く)"
        )
    legacy = set(re.findall(SLUG_RE, legacy_lines[0])) if len(legacy_lines) == 1 else set()

    headings = [line for line in text.splitlines() if re.match(r"### 全\d+本サマリ", line.strip())]
    if len(headings) != 1:
        bad.append(f"outline: 「### 全N本サマリ」の見出しが{len(headings)}件(1件にする)")
        return {}, second_pillar, legacy
    expected_rows = int(re.match(r"### 全(\d+)本サマリ", headings[0].strip()).group(1))
    calendar = section(text, headings[0].strip(), "outline", bad)
    if calendar is None:
        return {}, second_pillar, legacy
    plan, seen, marked_legacy = {}, 0, set()
    for line in calendar.splitlines():
        if not line.startswith("| ") or "---" in line or line.startswith("| 公開日"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(\(公開済\))?", cells[0])
        if not re.fullmatch(r"[a-z0-9-]+", cells[3]):
            continue
        if not m:
            bad.append(
                f"outline: 公開カレンダーの日付セルが不正: {cells[3]}={cells[0]!r}"
                "(YYYY-MM-DD または YYYY-MM-DD(公開済))"
            )
            continue
        date = parse_date(m.group(1), f"outline公開カレンダー({cells[3]})", bad)
        if not date:
            continue
        seen += 1
        slug = cells[3]
        if slug in plan:
            bad.append(f"outline: 公開カレンダーに重複slug: {slug}")
        if cells[5] not in PILLAR_VALUES:
            bad.append(f"outline: 公開カレンダーのピラー列が不正: {slug}={cells[5]!r}(許容: 空 / ● / ●(第2))")
        if m.group(2):
            marked_legacy.add(slug)
        plan[slug] = {
            "date": date,
            "category": split_category(cells[4], names, f"outline公開カレンダー({slug})", bad),
            "pillar": cells[5],
        }
    if seen != expected_rows or len(plan) != expected_rows:
        bad.append(
            f"outline: 公開カレンダーの行数={seen} / ユニークslug={len(plan)}"
            f"(見出しの宣言={expected_rows})"
        )
    # 「(公開済)」印は凡例が既存記事と宣言した行にだけ許す。日付が到来したからといって
    # 量産記事を既存記事へ再分類できると、詳細節も3〜5本の制約も同時に迂回できてしまう
    for slug in sorted(marked_legacy - legacy):
        bad.append(f"outline: 凡例が既存記事と宣言していないslugに「(公開済)」印がある: {slug}")
    for slug in sorted(legacy - marked_legacy):
        bad.append(f"outline: 既存記事と宣言されたslugが公開カレンダーで「(公開済)」印を持たない: {slug}")

    # 詳細節との双方向照合。行を全文から拾うと、詳細節の外(付録など)へ移すだけで
    # 「カレンダーにあるのに詳細節がない」の検査を素通りできる
    detail = {}
    detail_body = section(text, H_DETAIL, "outline", bad)
    for line in (detail_body or "").splitlines():
        if not line.startswith("- slug: `"):
            continue
        fields = {}
        for part in line[2:].split(" / "):
            key, _, value = part.partition(": ")
            fields[key.strip()] = value.strip()
        slug = fields.get("slug", "").strip("`")
        missing = [k for k in ("公開予定日", "カテゴリ", "ピラー") if k not in fields]
        if not slug or missing:
            bad.append(f"outline: 詳細節の項目が読み取れない({line[:60]}… 欠落={missing})")
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fields["公開予定日"]):
            bad.append(
                f"outline: 詳細節の公開予定日が YYYY-MM-DD ではない: {slug}={fields['公開予定日']!r}"
            )
            continue
        date = parse_date(fields["公開予定日"], f"outline詳細節({slug})", bad)
        if not date:
            continue
        if slug in detail:
            bad.append(f"outline: 詳細節に重複slug: {slug}")
        detail[slug] = {
            "date": date,
            "category": split_category(fields["カテゴリ"], names, f"outline詳細節({slug})", bad),
            "pillar": fields["ピラー"],
        }
    for slug in sorted(set(detail) - set(plan)):
        bad.append(f"outline: 詳細節にあるが公開カレンダーにないslug: {slug}")
    for slug in sorted(set(plan) - set(detail) - legacy):
        bad.append(f"outline: 公開カレンダーにあるが詳細節にないslug: {slug}")
    for slug, d in sorted(detail.items()):
        if slug not in plan:
            continue
        p = plan[slug]
        if p["date"] != d["date"]:
            bad.append(f"outline: 公開日がカレンダーと詳細節で不一致: {slug} {p['date']} / {d['date']}")
        if p["category"] != d["category"]:
            bad.append(
                f"outline: カテゴリがカレンダーと詳細節で不一致: {slug} "
                f"{p['category']} / {d['category']}"
            )
        if not re.fullmatch(r"No|Yes\(\d{2}[^)]*\)", d["pillar"]):
            bad.append(f"outline: 詳細節のピラー表記が不正: {slug}={d['pillar']!r}(No または Yes(NN…))")
        is_pillar = d["pillar"].startswith("Yes(")
        if bool(p["pillar"]) != is_pillar:
            bad.append(
                f"outline: ピラー指定がカレンダーと詳細節で不一致: {slug} "
                f"カレンダー={p['pillar'] or '(空)'} / 詳細節={d['pillar']}"
            )
        if is_pillar and ("第2" in p["pillar"]) != ("第2" in d["pillar"]):
            bad.append(f"outline: 第2ピラー表記がカレンダーと詳細節で不一致: {slug}")
        if is_pillar:
            num = re.match(r"Yes\((\d{2})", d["pillar"])
            if num and num.group(1) != d["category"]:
                bad.append(
                    f"outline: 詳細節のピラー番号がカテゴリと不一致: {slug} "
                    f"ピラー={d['pillar']} カテゴリ={d['category']}"
                )
    return plan, second_pillar, legacy


def check_selfcheck(text, indeg, rows, names, bad):
    """セルフチェック結果の数値・判定が実測と一致することを確認する。"""
    section_ = section(text, H_SELFCHECK, "link-matrix", bad)
    if section_ is None:
        return

    # チェック1: 総記事数・被リンク最小値と該当記事リスト
    m = re.search(r"\*\*PASS。\*\* (\d+)記事すべてが", section_)
    if not m:
        bad.append("セルフチェック1: 「**PASS。** N記事すべてが」の記述が見つからない")
    elif int(m.group(1)) != len(rows):
        bad.append(f"セルフチェック1: 総記事数の表記={m.group(1)} 実測={len(rows)}")
    m = re.search(r"最小は(\d+)で、該当は(\d+)記事[(\(]([^)）]*)[)\)]", section_)
    if not m:
        bad.append("セルフチェック1: 「最小は…で、該当は…記事(…)」の記述が読み取れない")
    else:
        want_min, want_count = int(m.group(1)), int(m.group(2))
        listed = re.findall(SLUG_RE, m.group(3))
        if len(listed) != len(set(listed)):
            bad.append("セルフチェック1: 最小リストにslugの重複がある")
        listed = set(listed)
        actual_min = min(indeg[s] for s in rows)
        actual = {s for s in rows if indeg[s] == actual_min}
        if want_min != actual_min:
            bad.append(f"セルフチェック1: 被リンク最小値 表={want_min} 実測={actual_min}")
        if want_count != len(listed):
            bad.append(f"セルフチェック1: 記事数の表記={want_count} 列挙={len(listed)}")
        for slug in sorted(listed - actual):
            bad.append(f"セルフチェック1: 最小リストの余分={slug}")
        for slug in sorted(actual - listed):
            bad.append(f"セルフチェック1: 最小リストの欠落={slug}")

    # チェック2: カテゴリごとのピラー/非ピラー最多の被リンク数と判定列
    categories = {row["category"] for row in rows.values()}
    seen = []
    for line in section_.splitlines():
        m = re.match(r"\| ((\d{2})[^|]*?)\s*\|", line)
        if not m:
            continue
        # カテゴリ列は番号だけでなく表示名も正規語彙と一致させる。番号しか見ないと
        # ここの表示名だけ差し替えても赤くならない
        num = split_category(m.group(1), names, "セルフチェック2", bad)
        seen.append(num)
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            bad.append(f"セルフチェック2: カテゴリ{num}の行の列数が足りない")
            continue
        members = {s for s in rows if rows[s]["category"] == num}
        top = {}
        for idx, is_pillar in ((1, True), (2, False)):
            found = re.findall(r"([a-z0-9-]+)\((\d+)", cells[idx])
            if len({s for s, _ in found}) != len(found):
                bad.append(f"セルフチェック2: カテゴリ{num}の{'ピラー' if is_pillar else '非ピラー'}欄にslugの重複がある")
            listed = dict(found)
            group = {s for s in members if bool(rows[s]["pillar"]) is is_pillar}
            label = "ピラー" if is_pillar else "非ピラー"
            for slug, count in listed.items():
                if slug not in group:
                    bad.append(f"セルフチェック2: カテゴリ{num}の{label}欄に不正なslug={slug}")
                elif indeg[slug] != int(count):
                    bad.append(f"セルフチェック2: カテゴリ{num} {slug} 表={count} 実測={indeg[slug]}")
            if is_pillar:
                for slug in sorted(group - set(listed)):
                    bad.append(f"セルフチェック2: カテゴリ{num}のピラー欄に欠落={slug}")
            elif group:
                best = max(indeg[s] for s in group)
                expected = {s for s in group if indeg[s] == best}
                if set(listed) != expected:
                    bad.append(
                        f"セルフチェック2: カテゴリ{num}の非ピラー最多 表={sorted(listed)} "
                        f"実測={sorted(expected)}(被リンク{best})"
                    )
            elif listed:
                bad.append(f"セルフチェック2: カテゴリ{num}に非ピラー記事はないが列挙されている")
            top[is_pillar] = max((indeg[s] for s in group), default=0)
        want = "○" if top[True] >= top[False] else "×"
        if not cells[3].startswith(want):
            bad.append(f"セルフチェック2: カテゴリ{num}の判定={cells[3]} 期待={want}")
        # 判定そのものが×なら設計が崩れている。表と実測が一致していても通さない
        if want != "○":
            bad.append(
                f"セルフチェック2: カテゴリ{num}のピラー被リンク({top[True]})が"
                f"非ピラー最多({top[False]})を下回っている。ピラーを見直す"
            )

    if len(seen) != len(set(seen)):
        bad.append(f"セルフチェック2: カテゴリ行が重複している({sorted(seen)})")
    if set(seen) != categories:
        bad.append(
            f"セルフチェック2: カテゴリ行={sorted(set(seen))} 関係表のカテゴリ={sorted(categories)}"
        )
    m = re.search(r"PASS\(全(\d+)カテゴリ\)", section_)
    if not m:
        bad.append("セルフチェック2: 「PASS(全Nカテゴリ)」の見出しが見つからない")
    elif int(m.group(1)) != len(categories):
        bad.append(
            f"セルフチェック2: 見出しの「全{m.group(1)}カテゴリ」が実数{len(categories)}と不一致"
        )


def main():
    bad = []
    missing = dist_missing()
    if missing:
        print(f"NG {missing}")
        return 1
    names = read_categories(bad)
    plan, second_pillar, legacy = read_plan(bad, names)
    commented, live, published, categories, body_paths, body_exempt = read_articles(bad)
    matrix_text, rows = read_matrix(bad, legacy, names)
    forward = read_forward(matrix_text, bad)
    written = {p.stem for p in (ROOT / "content/column").glob("*.md")} - NON_SEO_SLUGS
    now = today(bad)
    if now is None:
        for line in bad:
            print(f"NG {line}")
        return 1

    # 0. 記事集合と計画の包含関係。公開日が来た記事に実ファイルがなければ
    #    「有効化しろ」と促した先が404になる。逆に計画外の記事が混ざれば
    #    リンク設計の検査対象から丸ごと漏れる
    for slug in sorted(s for s in plan if plan[s]["date"] <= now and s not in written):
        bad.append(
            f"公開日が到来しているのに content/column/{slug}.md がない"
            f"(公開日={plan[slug]['date']})"
        )
    for slug in sorted(written - set(rows)):
        bad.append(f"content/column/{slug}.md が関係表にない(計画外の記事)")
    for slug in sorted(written - set(plan)):
        bad.append(f"content/column/{slug}.md が outline の公開カレンダーにない(計画外の記事)")

    # 0b. 凡例の「既存記事」宣言が実在・公開済みのslugだけを指すこと。ここが緩いと
    #     未来の記事をlegacyに書くだけで詳細節と3〜5本の制約を両方迂回できる
    for slug in sorted(legacy):
        if slug not in plan:
            bad.append(f"outline: 凡例の既存記事宣言が公開カレンダーにないslugを指す: {slug}")
        elif plan[slug]["date"] > now:
            bad.append(
                f"outline: 凡例の既存記事宣言が未公開のslugを指す: {slug}"
                f"(公開日={plan[slug]['date']} 基準日={now})"
            )
        if slug not in rows:
            bad.append(f"outline: 凡例の既存記事宣言が関係表にないslugを指す: {slug}")
        if slug not in written:
            bad.append(f"outline: 凡例の既存記事宣言に実ファイルがない: {slug}")

    # 1. 記事本文と関係表の双方向一致(執筆済み記事のみ)
    for source in sorted(written):
        in_table = set(rows.get(source, {}).get("targets", {}))
        in_body = {t for s, t in commented | live if s == source}
        for target in sorted(in_body - in_table):
            bad.append(f"関係表に未記載のリンク: {source} -> {target}")
        for target in sorted(in_table - in_body):
            if target in rows:  # 事業ページ等はカウント対象外
                bad.append(f"関係表にあるが本文にないリンク: {source} -> {target}")
        table_paths = rows.get(source, {}).get("paths", set())
        table_exempt = rows.get(source, {}).get("exempt", set())
        actual_paths = body_paths.get(source, set())
        actual_exempt = body_exempt.get(source, set())
        for path in sorted((table_paths | table_exempt) - (actual_paths | actual_exempt)):
            bad.append(f"関係表にあるが本文にないリンク: {source} -> {path}")
        # 本文にしかない設計リンクは、表の本数にも被リンク設計にも現れない抜け道になる
        for path in sorted(actual_paths - table_paths):
            bad.append(f"関係表に未記載のリンク: {source} -> {path}")
        for path in sorted(actual_paths | actual_exempt):
            if not path_exists(path):
                bad.append(f"本文のリンク先パスが実在しない: {source} -> {path}")

    # 1b. 本文の実リンク数も3〜5本に収まること(既存記事は対象外)。表だけを見ていると
    #     本文にだけリンクを足して設計本数を超えられる
    lo, hi = LINKS_PER_ARTICLE
    for source in sorted(written - legacy):
        if source not in rows:
            continue
        count = len({t for s, t in commented | live if s == source}) + len(body_paths.get(source, set()))
        if not lo <= count <= hi:
            bad.append(f"本文の実リンク数が{lo}〜{hi}本の範囲外: {source}={count}本")

    # 2. コメントアウトマーカーの整合(執筆済み記事のみ)
    for source in sorted(written):
        for target, seg in rows.get(source, {}).get("targets", {}).items():
            marked = MARKER in seg
            if (source, target) in commented and not marked:
                bad.append(f"※未公開マーカーが欠落: {source} -> {target}")
            if (source, target) in live and marked:
                bad.append(f"※未公開マーカーが過剰(本文では有効化済み): {source} -> {target}")

    # 2d. マーカーの要否を表全50行で公開日から決める。検査2は執筆済み記事しか見ないので、
    #     未執筆行はマーカーと前方参照一覧を同時に足し引きすれば整合して見えてしまう
    for source, row in sorted(rows.items()):
        for target, seg in sorted(row["targets"].items()):
            if source not in plan or target not in plan:
                continue
            marked = MARKER in seg
            # 「リンク元が公開される時点(既に過ぎているなら今日)でリンク先が未公開か」
            future = plan[target]["date"] > max(plan[source]["date"], now)
            if future and not marked:
                bad.append(
                    f"関係表: リンク先が未公開なのに※未公開マーカーがない: {source} -> {target}"
                    f"(リンク元={plan[source]['date']} リンク先={plan[target]['date']})"
                )
            if not future and marked:
                bad.append(
                    f"関係表: リンク先が公開済みなのに※未公開マーカーが残っている: {source} -> {target}"
                    f"(リンク元={plan[source]['date']} リンク先={plan[target]['date']})"
                )

    # 2e. (cross)注記がカテゴリ差と一致すること。片方だけ書き換えられると
    #     「カテゴリを跨ぐリンクを意識的に置いた」という記録が実態とズレる
    for source, row in sorted(rows.items()):
        for target, seg in sorted(row["targets"].items()):
            if target not in rows:
                continue
            noted = "(cross)" in seg
            crossing = rows[source]["category"] != rows[target]["category"]
            if crossing and not noted:
                bad.append(
                    f"関係表: カテゴリを跨ぐリンクに(cross)がない: {source}"
                    f"({rows[source]['category']}) -> {target}({rows[target]['category']})"
                )
            if not crossing and noted:
                bad.append(
                    f"関係表: 同一カテゴリのリンクに(cross)がある: {source} -> {target}"
                    f"(ともにカテゴリ{rows[source]['category']})"
                )

    # 2b. 関係表のリンク先slugが実在すること。事業ページは `/ai` のようにスラッシュ付きで
    #     書き別枠で扱うため、ここに残るのは必ずコラム記事slugである
    for source, row in sorted(rows.items()):
        for target in sorted(row["targets"]):
            if target not in rows:
                bad.append(f"関係表のリンク先が実在しないslug: {source} -> {target}")

    # 2c. 本文リンクは1記事3〜5本(style-guide.md §5)。既存記事は対象外
    for slug, row in sorted(rows.items()):
        if slug in legacy:
            continue
        if not lo <= row["links"] <= hi:
            bad.append(f"本文リンク先の本数が{lo}〜{hi}本の範囲外: {slug}={row['links']}本")

    # 3. 被リンク数の実測一致
    indeg = collections.Counter({s: 0 for s in rows})
    for source, row in rows.items():
        for target in row["targets"]:
            if target in rows and target != source:
                indeg[target] += 1
    for slug, row in rows.items():
        if row["cells"][4] != str(indeg[slug]):
            bad.append(f"被リンク数の不一致: {slug} 表={row['cells'][4]} 実測={indeg[slug]}")
    # 被リンク0は「どこからも辿れない記事」で、内部リンク設計としては欠陥。
    # セルフチェック1の記述と実測が揃っていても許さない(表と本文を同時に0へ
    # 書き換えれば一致はするので、一致検査だけでは孤立記事を見逃す)
    for slug in sorted(s for s in rows if indeg[s] < 1):
        bad.append(f"被リンクが0本の記事がある: {slug}(どのページからも辿れない)")

    # 4. 未公開マーカー付きペアと前方参照一覧の双方向一致(表全50行が対象)
    marked_pairs = {
        (source, target)
        for source, row in rows.items()
        for target, seg in row["targets"].items()
        if MARKER in seg and target in rows
    }
    for source, target in sorted(marked_pairs - set(forward)):
        bad.append(f"前方参照一覧に未記載: {source} -> {target}")
    for source, target in sorted(set(forward) - marked_pairs):
        bad.append(f"前方参照一覧の余分な行(関係表に未公開マーカーがない): {source} -> {target}")

    # 5. 前方参照一覧の日付がリンク元・リンク先とも計画と一致すること
    for (source, target), (source_date, target_date) in sorted(forward.items()):
        for slug, shown in ((source, source_date), (target, target_date)):
            if slug not in plan:
                bad.append(f"前方参照一覧: outlineに公開日がないslug: {slug}({source} -> {target})")
            elif plan[slug]["date"].strftime("%m-%d") != shown:
                bad.append(
                    f"前方参照一覧の日付ズレ: {source} -> {target} の {slug}({shown}) "
                    f"計画={plan[slug]['date'].strftime('%m-%d')}"
                )

    # 5b. 関係表とoutlineの公開カレンダーが同じ50本を指し、カテゴリ・ピラーも一致すること
    for slug in sorted(set(rows) - set(plan)):
        bad.append(f"関係表のslugがoutlineの公開カレンダーにない: {slug}")
    for slug in sorted(set(plan) - set(rows)):
        bad.append(f"outlineの公開カレンダーのslugが関係表にない: {slug}")
    for slug in sorted(set(rows) & set(plan)):
        if rows[slug]["category"] != plan[slug]["category"]:
            bad.append(
                f"カテゴリ不一致: {slug} 関係表={rows[slug]['category']} "
                f"outline={plan[slug]['category']}"
            )
        if bool(rows[slug]["pillar"]) != bool(plan[slug]["pillar"]):
            bad.append(
                f"ピラー指定の不一致: {slug} 関係表={rows[slug]['pillar'] or '(空)'} "
                f"outline={plan[slug]['pillar'] or '(空)'}"
            )
        elif ("第2" in rows[slug]["pillar"]) != ("第2" in plan[slug]["pillar"]):
            bad.append(f"第2ピラー表記の不一致: {slug} 関係表とoutlineで食い違っている")

    # 5c. ピラーはカテゴリごとにちょうど1本。第2ピラーはoutlineの凡例が宣言した1組だけ
    by_category = collections.defaultdict(list)
    for slug, row in rows.items():
        if row["pillar"]:
            by_category[(row["category"], row["pillar"])].append(slug)
    # 宣言が実在の組を指すことを先に確かめる。指さないまま実態を消せば
    # 「宣言=許可集合」の照合が両方とも空になり、整合して見えてしまう
    if second_pillar:
        category, slug = second_pillar
        if slug not in rows or slug not in plan:
            bad.append(f"outline: 凡例の第2ピラー宣言が実在しないslugを指す: {slug}")
        elif rows[slug]["category"] != category:
            bad.append(
                f"outline: 凡例の第2ピラー宣言のカテゴリが実態と不一致: {slug} "
                f"宣言={category} 関係表={rows[slug]['category']}"
            )
        elif rows[slug]["pillar"] != "●(第2)":
            bad.append(
                f"outline: 凡例が第2ピラーと宣言したslugに関係表の●(第2)がない: {slug}"
                f"(関係表={rows[slug]['pillar'] or '(空)'})"
            )
    for category in sorted({row["category"] for row in rows.values()}):
        main_pillars = sorted(by_category[(category, "●")])
        second = sorted(by_category[(category, "●(第2)")])
        if len(main_pillars) != 1:
            bad.append(
                f"カテゴリ{category}の主ピラー(●)が{len(main_pillars)}本: {main_pillars}(ちょうど1本にする)"
            )
        allowed = [second_pillar[1]] if second_pillar and second_pillar[0] == category else []
        if second != allowed:
            bad.append(
                f"カテゴリ{category}の第2ピラー={second} だが outline の凡例の宣言={allowed}。"
                "第2ピラーを増減するときは凡例も直す"
            )

    # 6. コメントアウト/有効化が公開日と噛み合っていること(執筆済み記事のみ)
    for source, target in sorted(commented):
        if source not in plan or target not in plan:
            continue
        if plan[target]["date"] <= max(plan[source]["date"], now):
            bad.append(
                f"公開済みリンクがコメントアウトのまま: {source} -> {target}"
                f"(リンク先公開日={plan[target]['date']})。週次リンクパッチで有効化する"
            )
    for source, target in sorted(live):
        if source not in plan or target not in plan:
            continue
        if plan[target]["date"] > max(plan[source]["date"], now):
            bad.append(
                f"未公開リンクが有効化されている: {source} -> {target}"
                f"(リンク先公開日={plan[target]['date']})。公開まではコメントアウトする"
            )

    # 6b. frontmatter の publishedDate・category が正本と一致すること
    for slug, date in sorted(published.items()):
        if slug in plan and plan[slug]["date"] != date:
            bad.append(
                f"frontmatterの publishedDate がoutlineと不一致: {slug} "
                f"記事={date} outline={plan[slug]['date']}"
            )
    for slug, value in sorted(categories.items()):
        if slug not in plan or not names:
            continue
        num = plan[slug]["category"]
        if num in names and value != names[num][1]:
            bad.append(
                f"frontmatterの category が正規語彙と不一致: {slug} 記事={value!r} "
                f"正本={names[num][1]!r}(計画カテゴリ{num})"
            )

    # 7. セルフチェック結果の実測一致
    check_selfcheck(matrix_text, indeg, rows, names, bad)

    for line in bad:
        print(f"NG {line}")
    print(
        f"check-link-matrix: 表{len(rows)}行 / 執筆済み{len(written)}記事 "
        f"(本文リンク: 有効{len(live)}・コメントアウト{len(commented)}), "
        f"前方参照{len(forward)}件, 基準日{now}, 違反 {len(bad)}件"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
