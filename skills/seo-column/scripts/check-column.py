#!/usr/bin/env python3
"""SEOコラム記事の機械チェック。

使い方: python3 scripts/check-column.py [slug ...]   (引数なしで content/column/ 全件)
チェック内容: frontmatter必須項目・description字数・faq数・本文文字数・
内部リンク先の実在(outline計画slug含む)・禁止表現・公開日のoutline整合・混入文字。
v3追加: 図版ファイルの実在・alt・キャプション・プレースホルダ残存・
素材台帳の権利判定・ブリーフとの図版点数突合(pipeline-v3.md §チェッカーに追加する項目)・
supervisor が src/data/supervisors.ts に定義済みのIDか。
終了コード: エラーありで1。WARNは0のまま。
"""
import datetime
import re
import sys
import unicodedata
from pathlib import Path

from seo_column_lib import DocsError, load_categories

ROOT = Path(__file__).resolve().parent.parent
COLUMN_DIR = ROOT / "content" / "column"
OUTLINE = ROOT / "docs" / "seo-column" / "outline.md"
BRIEFS_DIR = ROOT / "docs" / "seo-column" / "briefs"
SUPERVISORS_TS = ROOT / "src" / "data" / "supervisors.ts"


def _load_categories():
    """frontmatter category の正規語彙を style-guide.md の表から読む。

    ここにハードコードすると正本を書き換えても検査が追随しない。読み方は
    check-link-matrix.py と共有する(seo_column_lib)。片方だけがコードブロックを
    除かない・片方だけが重複を見逃す、という形でズレるのを避けるため。
    """
    try:
        return {value for _, value in load_categories(ROOT).values()}
    except DocsError as e:
        raise SystemExit(f"style-guide.md: {e}")


ALLOWED_CATEGORIES = _load_categories()
# 技術記事シリーズ「自社をAI業務標準書で動かす実装記録」のカテゴリ(SEO 12語彙の外)
TECH_SERIES_CATEGORY = "AI駆動開発"

# 実名NG(既公開記事に存在しないクライアント名)・架空企業名
# 下記はサンプル値。自分のサイトで使う場合は、既公開のcases/topics記事に無い実在クライアント名、
# および引用禁止にしたい架空企業名に置き換えること。
FORBIDDEN = ["非公開クライアントA", "架空企業サンプル"]
FORBIDDEN_WORD = [r"\b非公開クライアントB\b"]

BODY_MIN, BODY_MAX = 4000, 8000
DESC_MIN, DESC_MAX = 80, 120

# 図版の埋め込みは自分自身へのリンクで包む形(pipeline-v3.md Stage 4)
FIG_EMBED = re.compile(r"\[!\[(?P<alt>.*?)\]\((?P<img>/images/[^)\s]+)\)\]\((?P<href>/images/[^)\s]+)\)")
BARE_IMG = re.compile(r"(?<!\[)!\[(?P<alt>.*?)\]\((?P<img>/images/[^)\s]+)\)")
CAPTION = re.compile(r"^\*図\s*(\d+)\s*[:：].+\*$")
FIG_PLACEHOLDER = re.compile(r"<!--\s*FIG:\s*\d+\s*-->")
# ブリーフの図版点数: バッチ1形式「図版点数: **2点**」/ パイロット形式「判定結果: **2点**」
BRIEF_FIG_COUNT = re.compile(r"(?:図版点数|判定結果)\s*[:：]\s*\*\*\s*(\d+)\s*点\*\*")


def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return None, text
    return m.group(1), m.group(2)


def outline_plan():
    """outline.mdのサマリ表から slug -> 公開予定日 を取る"""
    plan = {}
    if not OUTLINE.exists():
        return plan
    for line in OUTLINE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(\d{4}-\d{2}-\d{2})[^|]*\|\s*\d+\s*\|[^|]*\|\s*([a-z0-9-]+)\s*\|", line)
        if m:
            plan[m.group(2)] = m.group(1)
    return plan


def supervisor_ids():
    """src/data/supervisors.ts の SUPERVISORS に定義されたキーを取る。
    typoで存在しないIDを書くと監修ブロックが黙って出なくなるのでチェッカーで拾う。"""
    if not SUPERVISORS_TS.exists():
        return None
    text = SUPERVISORS_TS.read_text(encoding="utf-8")
    m = re.search(r"SUPERVISORS[^=]*=\s*\{(.*)", text, re.S)
    if not m:
        return None
    return set(re.findall(r"^  ([A-Za-z0-9_]+):\s*\{", m.group(1), re.M))


def check_assets_ledger(slug):
    """素材台帳 briefs/{slug}.assets.md の権利判定欄が埋まっているか"""
    errors = []
    ledger = BRIEFS_DIR / f"{slug}.assets.md"
    if not ledger.exists():
        return errors
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or cells[0] in ("ファイル", "") or set(cells[0]) <= {"-", ":"}:
            continue
        if not cells[4]:
            errors.append(f"素材台帳の権利判定が空: {cells[0]}({ledger.name})")
    return errors


def check_figures(slug, body):
    """v3の図版チェック。埋め込み形式・実ファイル・alt・キャプション・ブリーフ突合"""
    errors, warns = [], []
    lines = body.splitlines()

    if FIG_PLACEHOLDER.search(body):
        errors.append("プレースホルダ <!-- FIG:n --> が残っている(Stage 4未完)")

    own_prefix = f"/images/column/{slug}/"
    has_reshown = any(
        own_prefix not in m.group("img")
        for m in (FIG_EMBED.search(l) for l in lines) if m
    )
    count = 0       # 自記事の図の点数(ブリーフ突合用。他記事からの再掲は数えない)
    for i, line in enumerate(lines):
        m = FIG_EMBED.search(line)
        if not m:
            bare = BARE_IMG.search(line)
            if bare and "/images/column/" in bare.group("img"):
                warns.append(f"図版が自分自身へのリンクで包まれていない: {bare.group('img')}")
            continue
        img, href, alt = m.group("img"), m.group("href"), m.group("alt").strip()
        if own_prefix in img:
            count += 1

        if not alt:
            errors.append(f"altが空: {img}")
        if img != href:
            errors.append(f"画像パスとリンク先が不一致: {img} → {href}")
        if not (ROOT / "content" / img.lstrip("/")).exists():
            errors.append(f"図版ファイルがない: content{img}")

        # 直後の非空行がキャプションであること
        caption = next((lines[j] for j in range(i + 1, len(lines)) if lines[j].strip()), None)
        cm = CAPTION.match(caption.strip()) if caption else None
        if not cm:
            errors.append(f"図の直下にキャプション行(*図N: …*)がない: {img}")
        else:
            # 他記事の図を再掲している記事では番号が振り直されるため、
            # 自記事の図だけで構成される場合に限りファイル名の番号と突合する
            fn = re.search(r"fig-(\d+)", img)
            if not has_reshown and fn and fn.group(1) != cm.group(1):
                errors.append(f"図番号の不一致: {img} のキャプションが図{cm.group(1)}")

    # ブリーフの図版計画との突合
    brief = BRIEFS_DIR / f"{slug}.md"
    if not brief.exists():
        if count:
            warns.append(f"図{count}点あるがブリーフ({brief.name})がない")
        return errors, warns
    text = brief.read_text(encoding="utf-8")
    bm = BRIEF_FIG_COUNT.search(text)
    if bm:
        planned = int(bm.group(1))
        if planned != count:
            errors.append(f"図版点数がブリーフと不一致: 計画{planned}点 / 本文{count}点")
    elif "図版なし" in text:
        if count:
            errors.append(f"ブリーフは「図版なし」だが本文に図が{count}点ある")
    else:
        warns.append(f"ブリーフから図版点数を読めない({brief.name})")

    return errors, warns


def check_raw_html_assets(body):
    """raw HTML参照の実在チェック(DLカード系以外の生HTML)。
    Astroビルドはmd内のraw HTMLが指す画像・ファイルを検証しないため、
    コミット漏れが本番404になる(PR #202のBlockerで実際に起きた)。
    dl-cardは <!-- dl-card: slug --> マーカーに置き換わり本文には生HTMLが残らないため、
    dl-card自体のassetチェックは check_dl_card_registry() が担う。ここは万一
    dl-card以外の生<img>/xlsxリンクが本文に混入した場合の保険として残す。
    - <img src="/images/..."> は content/ 配下に実体があり、altが空でないこと。
      ただし aria-hidden="true" の装飾画像(直後に同名テキストがあるツールロゴ等)は
      空altが正(WCAG 1.1.1。非空altだと読み上げが重複する)
    - dl-preview-<hash8>.webp はハッシュがファイル実体のMD5先頭8桁と一致すること
    - <a href="/downloads/*.xlsx"> は public/downloads/ に実体があること
    """
    import hashlib
    errors = []
    for m in re.finditer(r"<img\b[^>]*>", body):
        tag = m.group(0)
        src = re.search(r'src="(/images/[^"]+)"', tag)
        if not src:
            continue
        f = ROOT / "content" / src.group(1).lstrip("/")
        if not f.exists():
            errors.append(f"raw HTML画像の実体がない: content{src.group(1)}")
        else:
            hm = re.search(r"dl-preview-([0-9a-f]{8})\.webp$", src.group(1))
            if hm and hashlib.md5(f.read_bytes()).hexdigest()[:8] != hm.group(1):
                errors.append(f"dl-previewのハッシュが実体と不一致: {src.group(1)}")
        alt = re.search(r'alt="([^"]*)"', tag)
        decorative = 'aria-hidden="true"' in tag
        if decorative:
            if not alt:
                errors.append(f"装飾画像(aria-hidden)にalt属性がない: {src.group(1)}")
            elif alt.group(1).strip():
                errors.append(f"装飾画像(aria-hidden)のaltが非空: {src.group(1)}")
        elif not alt or not alt.group(1).strip():
            errors.append(f"raw HTML画像のaltが空: {src.group(1)}")
    for dm in re.finditer(r'href="(/downloads/[^"]+\.xlsx)"', body):
        if not (ROOT / "public" / dm.group(1).lstrip("/")).exists():
            errors.append(f"配布ファイルの実体がない: public{dm.group(1)}")
    return errors


DL_CARDS_JSON = ROOT / "src" / "data" / "dl-cards.json"
DL_CARD_MARKER = re.compile(r"<!--\s*dl-card:\s*([a-z0-9-]+)\s*-->")

# 内部リンクカード <!-- link-card: slug -->(src/lib/remark-link-card.mjs)。
# dl-cardと違いレジストリを持たず、リンク先記事のfrontmatterをビルド時にfsで読んで
# 組み立てる。ここでは remark プラグインがビルド時に例外で止める条件(記事の実在・
# frontmatter必須項目)を先回りで検査し、内部リンク同様の公開日整合も見る。
LINK_CARD_MARKER = re.compile(r"<!--\s*link-card:\s*([a-z0-9-]+)\s*-->")


def check_link_card_targets(slug, text, plan, all_slugs, today):
    """リンクカードのマーカーが指す記事の実在・frontmatter・公開日整合を検査する。
    生リンク(],( /column/xxx)) の未来公開チェック(check_file本体)と同じ規則を、
    HTMLコメントのため生リンクの正規表現には掛からないマーカーにも独立して適用する。
    """
    errors = []
    fm, _ = parse_frontmatter(text)
    pub = None
    if fm:
        m = re.search(r"^publishedDate:\s*(.+)$", fm, re.M)
        if m:
            pub = m.group(1).strip().strip("'\"")
    for target in LINK_CARD_MARKER.findall(text):
        if target == slug:
            errors.append(f"リンクカードが自己参照している: {target}")
            continue
        if target not in all_slugs and target not in plan:
            errors.append(f"リンクカード先が計画に存在しない: {target}")
            continue
        if pub and target in plan and plan[target] > max(pub, today):
            errors.append(f"リンクカード先が未公開: {target}({plan[target]}公開)は本文に置けません")
        target_path = COLUMN_DIR / f"{target}.md"
        if not target_path.exists():
            # 未執筆(計画のみ)。ビルド時にremark-link-cardが例外で止まるので
            # 公開日チェックが通っていてもここでは常にエラーにする
            errors.append(f"リンクカード先の記事ファイルがない(未執筆): content/column/{target}.md")
            continue
        t_text = target_path.read_text(encoding="utf-8")
        t_fm, _ = parse_frontmatter(t_text)
        if t_fm is None:
            errors.append(f"リンクカード先にfrontmatterがない: {target}")
            continue
        for key in ("title", "category", "excerpt"):
            if not re.search(rf"^{key}:", t_fm, re.M):
                errors.append(f"リンクカード先のfrontmatterに{key}がない: {target}")
        thumb_m = re.search(r"^thumbnail:\s*(.+)$", t_fm, re.M)
        if thumb_m:
            thumb_path = thumb_m.group(1).strip().strip("'\"")
            if not (ROOT / "content" / thumb_path.lstrip("/")).exists():
                errors.append(f"リンクカード先のthumbnail実体がない: {target} -> {thumb_path}")
    return errors


def load_dl_cards():
    """DLサンプルカードのレジストリ(src/data/dl-cards.json)を読む。
    dl-card自体は astro.config.mjs の remarkDlCard がビルド時に展開するため
    check-column.pyの対象ではないが、レジストリが指す実体ファイルとマーカーの
    整合はここで検査する(remarkプラグインは実体の存在チェックまではしないため)。
    """
    if not DL_CARDS_JSON.exists():
        return None
    import json

    return json.loads(DL_CARDS_JSON.read_text(encoding="utf-8"))


def check_dl_card_registry(slug, body, registry):
    """dl-cardマーカーとレジストリの整合、レジストリが指す実体ファイルの存在を検査する。
    - 本文のマーカーが指すslugがレジストリに無い→エラー(ビルド時にremarkDlCardが例外で止まるのと同じ条件を先回りで拾う)
    - レジストリの previewSrc(画像)・downloadHref(配布ファイル)の実体が無い→エラー
    - previewAlt が空→エラー(altチェックの移設)
    """
    errors = []
    if registry is None:
        return errors
    for marker_slug in DL_CARD_MARKER.findall(body):
        if marker_slug not in registry:
            errors.append(f"dl-cardマーカーのslugがレジストリ(dl-cards.json)にない: {marker_slug}")

    entry = registry.get(slug)
    if entry is None:
        return errors
    if not DL_CARD_MARKER.search(body):
        errors.append(f"レジストリに dl-cards.json[{slug}] があるが本文に <!-- dl-card: {slug} --> マーカーがない")

    preview_src = entry.get("previewSrc", "")
    f = ROOT / "content" / preview_src.lstrip("/")
    if not f.exists():
        errors.append(f"dl-card previewSrcの実体がない: content{preview_src}")
    else:
        import hashlib

        hm = re.search(r"dl-preview-([0-9a-f]{8})\.webp$", preview_src)
        if hm and hashlib.md5(f.read_bytes()).hexdigest()[:8] != hm.group(1):
            errors.append(f"dl-previewのハッシュが実体と不一致: {preview_src}")
    if not (entry.get("previewAlt") or "").strip():
        errors.append(f"dl-card previewAltが空: {slug}")

    download_href = entry.get("downloadHref", "")
    if download_href and not (ROOT / "public" / download_href.lstrip("/")).exists():
        errors.append(f"dl-card配布ファイルの実体がない: public{download_href}")

    return errors


def check_file(path, plan, all_slugs, sup_ids=None, dl_cards=None):
    errors, warns = [], []
    text = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    if fm is None:
        return [f"frontmatterがない"], []

    def fm_get(key):
        m = re.search(rf"^{key}:\s*(.+)$", fm, re.M)
        return m.group(1).strip().strip("'\"") if m else None

    # 技術記事シリーズ(category: AI駆動開発)はSEO量産記事ではないため、
    # faq(FAQ構造化データ)とSEOカテゴリ語彙の検査対象から外す。他の検査は同じ
    is_tech_series = (fm_get("category") == TECH_SERIES_CATEGORY)
    required = ["title", "slug", "category", "description", "excerpt", "publishedDate", "updatedDate", "author", "keywords"]
    if not is_tech_series:
        required.append("faq")
    for key in required:
        if not re.search(rf"^{key}:", fm, re.M):
            errors.append(f"frontmatter欠落: {key}")

    if re.search(r"^status:", fm, re.M):
        warns.append("statusフィールドあり(量産記事では付けない運用)")

    slug = fm_get("slug")
    if slug and slug != path.stem:
        errors.append(f"slug({slug})とファイル名({path.stem})が不一致")

    cat = fm_get("category")
    if cat and cat not in ALLOWED_CATEGORIES and not is_tech_series:
        errors.append(f"category「{cat}」が正規語彙にない(style-guide.md補足参照)")

    desc = fm_get("description")
    if desc and not (DESC_MIN <= len(desc) <= DESC_MAX):
        warns.append(f"description {len(desc)}字(基準{DESC_MIN}〜{DESC_MAX})")

    author = fm_get("author")
    if author and author != "株式会社ピネアル":
        errors.append(f"author表記: {author}(正: 株式会社ピネアル)")
    if "ピネアル株式会社" in text:
        errors.append("誤記「ピネアル株式会社」(正: 株式会社ピネアル)")

    sup = fm_get("supervisor")
    if sup and sup_ids is not None and sup not in sup_ids:
        errors.append(f"supervisor「{sup}」がsupervisors.tsに未定義(定義済み: {', '.join(sorted(sup_ids)) or 'なし'})")

    faq_count = len(re.findall(r"^\s+- q:", fm, re.M))
    if not (3 <= faq_count <= 4):
        warns.append(f"faq {faq_count}問(基準3〜4)")

    body_len = len(re.sub(r"\s", "", body))
    if not (BODY_MIN <= body_len <= BODY_MAX):
        warns.append(f"本文{body_len}字(基準{BODY_MIN}〜{BODY_MAX})")

    pub = fm_get("publishedDate")
    if slug in plan and pub != plan[slug]:
        errors.append(f"publishedDate({pub})がoutline計画({plan[slug]})と不一致")

    # 内部リンク: /column/xxx はコメントアウト含め計画slugに存在すること
    for target in re.findall(r"\]\(/column/([a-z0-9-]+)/?\)", text):
        if target not in all_slugs and target not in plan:
            errors.append(f"リンク先が計画に存在しない: /column/{target}")
    # 生リンク(コメント外)は、リンク元が読める時点でリンク先も公開済みであること(未来分は404になる)。
    # リンク元公開日と今日の遅い方を基準にする(週次リンクパッチで後から有効化したリンクを誤検知しないため)。
    # 「今日」は公開制御の正本 src/lib/content.ts todayJST() と同じJST基準で取る。
    # date.today()だとUTCのCIランナーでJST当日公開分の有効化が前日扱いになりNGを誤検知する
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date().isoformat()
    live_text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for target in re.findall(r"\]\(/column/([a-z0-9-]+)/?\)", live_text):
        if pub and target in plan and plan[target] > max(pub, today):
            errors.append(f"生リンク先が未公開: /column/{target}({plan[target]}公開)はコメントアウトが必要")
    # コメントアウトリンクの書式ずれ(<!--内に複数リンク等)は目視に委ねWARNのみ
    commented = len(re.findall(r"<!--[^>]*\[", text))
    if commented:
        warns.append(f"コメントアウトリンク{commented}箇所(週次パッチ対象)")

    for name in FORBIDDEN:
        if name in text:
            errors.append(f"禁止表現: {name}")
    for pat in FORBIDDEN_WORD:
        if re.search(pat, text):
            errors.append(f"禁止表現(実名不可): {pat}")

    fig_errors, fig_warns = check_figures(path.stem, body)
    errors += fig_errors
    warns += fig_warns
    errors += check_assets_ledger(path.stem)
    errors += check_raw_html_assets(body)
    errors += check_dl_card_registry(path.stem, body, dl_cards)
    errors += check_link_card_targets(path.stem, text, plan, all_slugs, today)

    for ch in set(text):
        if unicodedata.category(ch).startswith("L"):
            name = unicodedata.name(ch, "")
            if name.startswith(("CYRILLIC", "HANGUL", "THAI", "ARABIC")):
                errors.append(f"混入文字: {ch} ({name})")
                break

    return errors, warns


COLUMN_GROUPS_TS = ROOT / "src" / "data" / "column-groups.ts"


def check_column_groups_coverage():
    """/column 一覧の読者別区分(src/data/column-groups.ts)が正規語彙表と同期しているかを見る。

    ここが古いままだと、style-guide.md にカテゴリを1件追加してもハブ側の区分に
    現れず、フィルタピルが「その他」に落ちたまま気づかれない(2026-08 ハブ実装で新設)。
    TSの中身は実行できないので簡易な文字列抽出。境界を厳密に判定する必要はなく、
    正規語彙が1件でも列に出ていなければ検知できれば足りる。
    """
    if not COLUMN_GROUPS_TS.exists():
        return [f"{COLUMN_GROUPS_TS.name}が存在しない"]
    text = COLUMN_GROUPS_TS.read_text(encoding="utf-8")
    known = set(re.findall(r"'([^']+)'", text))
    missing = sorted((ALLOWED_CATEGORIES | {TECH_SERIES_CATEGORY}) - known)
    if missing:
        return [f"column-groups.tsにカテゴリ未収録: {', '.join(missing)}"]
    return []


def main():
    plan = outline_plan()
    files = sorted(COLUMN_DIR.glob("*.md"))
    if len(sys.argv) > 1:
        files = [COLUMN_DIR / f"{s}.md" for s in sys.argv[1:]]
    all_slugs = {p.stem for p in COLUMN_DIR.glob("*.md")}
    sup_ids = supervisor_ids()
    dl_cards = load_dl_cards()
    failed = 0
    for path in files:
        if not path.exists():
            print(f"[ERROR] {path.name}: ファイルなし")
            failed += 1
            continue
        errors, warns = check_file(path, plan, all_slugs, sup_ids, dl_cards)
        status = "NG" if errors else "OK"
        print(f"[{status}] {path.name}")
        for e in errors:
            print(f"    ERROR: {e}")
        for w in warns:
            print(f"    WARN: {w}")
        if errors:
            failed += 1

    # レジストリにあるのに、どの記事にもマーカーが無い項目(全件走査時のみ判定可能)
    if dl_cards and len(sys.argv) <= 1:
        marked_slugs = set()
        for p in COLUMN_DIR.glob("*.md"):
            marked_slugs |= set(DL_CARD_MARKER.findall(p.read_text(encoding="utf-8")))
        orphan_entries = sorted(set(dl_cards) - marked_slugs)
        if orphan_entries:
            print(f"[NG] dl-cards.json: マーカーの無いレジストリ項目 {len(orphan_entries)}件")
            for s in orphan_entries:
                print(f"    ERROR: レジストリに dl-cards.json[{s}] があるがどの記事にも <!-- dl-card: {s} --> マーカーがない")
            failed += 1

    if len(sys.argv) <= 1:
        group_errors = check_column_groups_coverage()
        if group_errors:
            print(f"[NG] {COLUMN_GROUPS_TS.name}")
            for e in group_errors:
                print(f"    ERROR: {e}")
            failed += 1

    print(f"\n{len(files)}件中 NG {failed}件")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
