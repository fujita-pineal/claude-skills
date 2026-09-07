#!/usr/bin/env python3
"""check-column.py と check-link-matrix.py が共有する docs の読み方。

同じ正本(`docs/seo-column/style-guide.md` のカテゴリ表)を2つのcheckerが別々の
前処理で読んでいると、片方だけがコードブロックを除かない・片方だけが重複を
検査しない、といったズレが出る。読み方をここに1本化する。
"""
import re


class DocsError(Exception):
    """正本の書式が壊れていて読めない。"""


def visible(text):
    """HTMLコメントを落とす。コメントアウトした記述を「書いてある」と数えないため。"""
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def strip_blocks(text):
    """コードブロックを落とす。CommonMarkの3記法すべてを対象にする。

    フェンスは開始記号と同じ文字を開始長以上並べた行だけを閉じとみなし(情報文字列は
    開始行にしか置けない)、閉じがなければ文末までコードとして扱う。開始・終了とも
    字下げは3桁まで(4桁以上はフェンスではなく字下げコード)。字下げコードは
    リストの継続行と紛らわしいので、リスト項目が続いている間の4スペースは残し、
    その内側にさらに1段字下げされた行(リストの中のコードブロック)は落とす。

    インラインコードはここでは残す(docsのslug表記が `xxx` なので消せない)。
    """
    def opener(line, limit):
        """フェンスの開始/終了行なら記号を返す。字下げはCommonMark同様3桁まで。"""
        m = re.match(r"(?P<indent>[ \t]*)(?P<f>`{3,}|~{3,})", line)
        if not m:
            return None
        if len(m.group("indent").expandtabs(4)) > limit + 3:
            return None
        return m.group("f")

    out, fence, fence_indent, list_indent = [], None, 0, None
    for line in text.splitlines():
        if fence is not None:
            out.append("")
            closing = opener(line, fence_indent)
            if (
                closing
                and re.match(r"[ \t]*(?:`{3,}|~{3,})[ \t]*$", line)
                and closing[0] == fence[0]
                and len(closing) >= len(fence)
            ):
                fence = None
            continue
        found = opener(line, list_indent or 0)
        if found:
            fence, fence_indent = found, list_indent or 0
            out.append("")
            continue
        if not line.strip():
            out.append(line)
            continue
        item = re.match(r"(?P<indent>[ \t]*)(?:[-*+]|\d+\.)[ \t]", line)
        if item:
            # リスト項目の本文が始まる位置。ここから4スペース以上はコード
            list_indent = len(item.group("indent").expandtabs(4)) + 2
            out.append(line)
            continue
        indent = len(line) - len(line.lstrip(" \t"))
        indent = len(line[:indent].expandtabs(4))
        if list_indent is not None and indent >= list_indent:
            out.append("" if indent >= list_indent + 4 else line)
            continue
        list_indent = None
        out.append("" if indent >= 4 else line)
    return "\n".join(out)


def find_section(text, heading):
    """見出し「行」に完全一致した節を切り出し、同じ階層の次の見出しで打ち切る。

    部分一致にすると「## セルフチェック結果(旧)」へ改名するだけで検査対象を
    空にできる。重複見出しもどちらが正か決まらないので読めないものとして扱う。
    """
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if line.strip() == heading]
    if not hits:
        raise DocsError(f"見出し「{heading}」が見つからない")
    if len(hits) > 1:
        raise DocsError(f"見出し「{heading}」が{len(hits)}件ある(1件にする)")
    level = len(heading) - len(heading.lstrip("#"))
    start = hits[0] + 1
    stop = len(lines)
    for i in range(start, len(lines)):
        m = re.match(r"(#{1,6}) ", lines[i])
        if m and len(m.group(1)) <= level:
            stop = i
            break
    return "\n".join(lines[start:stop])


CATEGORIES_HEADING = "## 補足: frontmatter category の正規語彙(2026-08-04確定)"


def load_categories(root):
    """style-guide.md の正規語彙表から {番号: (計画カテゴリ名, frontmatter値)} を読む。

    第1列は計画カテゴリ名、第2列は frontmatter の `category` に書く値。categoryは
    一覧フィルタと関連記事の完全一致選定に使うので、番号・カテゴリ名・frontmatter値の
    どれも重複させない。
    """
    path = root / "docs" / "seo-column" / "style-guide.md"
    # コード除去が先。フェンスの中の `<!--` は本文のコメント開始ではないので、
    # 先にコメントを消すとフェンス外の `-->` までまとめて飲み込まれる
    text = visible(strip_blocks(path.read_text(encoding="utf-8")))
    body = find_section(text, CATEGORIES_HEADING)
    names = {}
    for line in body.splitlines():
        m = re.match(r"\|\s*(\d{2}) ([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
        if not m:
            continue
        num, plan_name, fm_name = m.group(1), m.group(2), m.group(3)
        # 「AX/DX (公開済み1本目と同一表記)」のような補足は値ではない
        fm_name = re.sub(r"\s+\(.*\)$", "", fm_name)
        if num in names:
            raise DocsError(f"正規語彙表にカテゴリ番号の重複: {num}")
        names[num] = (plan_name, fm_name)
    if not names:
        raise DocsError("正規語彙表からカテゴリを1件も読めない")
    for column, label in ((0, "カテゴリ名"), (1, "frontmatter値")):
        seen = {}
        for num, values in sorted(names.items()):
            if values[column] in seen:
                raise DocsError(
                    f"正規語彙表の{label}が重複: {values[column]!r}"
                    f"(カテゴリ{seen[values[column]]} と {num})"
                )
            seen[values[column]] = num
    return names
