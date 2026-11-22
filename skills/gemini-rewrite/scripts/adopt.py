#!/usr/bin/env python3
"""記事モードの出力(final.md)を原文に当てる。既定は全片採用で、戻すのは閉じた理由に当たる片だけ。
usage:
  adopt.py list  <orig.md> <final.md>                         変更片を番号つきで出す
  adopt.py apply <orig.md> <final.md> <out.md> [--revert 3:fact,7:tone]
                                                              指定した片だけ原文に戻して out.md を書き、採用率を出す
片は「文(。まで)か改行で区切った単位」の差分のかたまり。並びは list と apply で同じ。
戻す理由は REASONS の5つだけ。「原文の言い回しの方が好き」「書き手の声」は理由にならない(方針: Gemini の案をなるべく採用する)。"""
import argparse, difflib, re, sys

REASONS = {
    "fact": "照合で残った fact_changed の指摘、または数値・固有名詞・限定の語が動いた",
    "dict5": "辞書5 の Fail 語、ダッシュ、擬人化、読者感情の決めつけが入った",
    "tone": "文末の丁寧さ(敬体/常体)か一人称が原文から変わった",
    "kango": "和語が漢語に置き換わり、語だけ戻しても文が硬いまま",
    "keep": "守る段落(引用、顧客の原文、CTA、連載案内、見出し)",
}
DICT5_FAIL = ["非常に", "極めて", "大幅に", "飛躍的に", "格段に", "この度は", "昨今", "言うまでもなく", "――", "—", "–"]


def tokens(text):
    # 連結すると元の文字列に完全に戻る分割
    return re.findall(r"[^。\n]*。|[^。\n]+|\n", text)


def hunks(orig, final):
    """空行だけの差は片に数えず、原文の改行を残す(Gemini は節末の空行を落とす)。"""
    a, b = tokens(orig), tokens(final)
    ops = []
    for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        tag, i1, i2, j1, j2 = op
        if tag != "equal" and not "".join(a[i1:i2]).strip() and not "".join(b[j1:j2]).strip():
            op = ("blank", i1, i2, j1, j2)
        ops.append(op)
    return a, b, ops


def kanji_new(orig_all, n):
    """原文全体に出てこない漢字2字以上の語。隣の片から移っただけの語は拾わない。"""
    pat = r"[一-龥々]{2,}"
    return sorted({w for w in re.findall(pat, n) if w not in orig_all})


def cmd_list(a_):
    orig, final = open(a_.orig).read(), open(a_.final).read()
    a, b, ops = hunks(orig, final)
    k = 0
    for tag, i1, i2, j1, j2 in ops:
        if tag in ("equal", "blank"):
            continue
        k += 1
        o, n = "".join(a[i1:i2]).strip("\n"), "".join(b[j1:j2]).strip("\n")
        hints = []
        kn = kanji_new(orig, n)
        if kn:
            hints.append("新しい漢語: " + "、".join(kn[:6]))
        d5 = [w for w in DICT5_FAIL if w in n and w not in o]
        if d5:
            hints.append("辞書5: " + "、".join(d5))
        print(f"[{k}] {tag}" + (f"  ({' / '.join(hints)})" if hints else ""))
        print("  - " + (o.replace("\n", "\n    ") or "(なし)"))
        print("  + " + (n.replace("\n", "\n    ") or "(なし)"))
    print(f"\n変更片 {k}件。戻す片だけ `--revert 番号:理由` で指定する。理由は {', '.join(REASONS)}")


def cmd_apply(a_):
    orig, final = open(a_.orig).read(), open(a_.final).read()
    a, b, ops = hunks(orig, final)
    rev = {}
    for x in filter(None, a_.revert.split(",")):
        num, _, why = x.strip().partition(":")
        if why not in REASONS:
            sys.exit(f"戻す理由「{why}」は使えない。使えるのは {', '.join(f'{r}({d})' for r, d in REASONS.items())}")
        rev[int(num)] = why
    out, k = [], 0
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            out += b[j1:j2]; continue
        if tag == "blank":
            out += a[i1:i2]; continue
        k += 1
        out += a[i1:i2] if k in rev else b[j1:j2]
    bad = sorted(set(rev) - set(range(1, k + 1)))
    if bad:
        sys.exit(f"片番号 {bad} は存在しない(変更片は {k}件)")
    open(a_.out, "w").write("".join(out))
    by = {}
    for why in rev.values():
        by[why] = by.get(why, 0) + 1
    rate = (k - len(rev)) / k * 100 if k else 100.0
    print(f"変更片 {k}件、採用 {k - len(rev)}件、戻し {len(rev)}件(採用率 {rate:.0f}%)"
          + ("。戻した理由: " + "、".join(f"{w} {c}件" for w, c in sorted(by.items())) if by else ""))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("list"); p.add_argument("orig"); p.add_argument("final")
    p = sp.add_parser("apply"); p.add_argument("orig"); p.add_argument("final"); p.add_argument("out")
    p.add_argument("--revert", default="")
    a_ = ap.parse_args()
    {"list": cmd_list, "apply": cmd_apply}[a_.cmd](a_)


if __name__ == "__main__":
    main()
