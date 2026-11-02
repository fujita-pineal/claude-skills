#!/usr/bin/env python3
"""推敲の前後を比べ、変えてはいけない部分の変更を検出する。

使い方: guard.py <前の版> <後の版> [--protect-after 文字列]
違反がなければ終了コード0、あれば1を返す。
主張の強さ、帰属、留保の変化は検出しない。そこは人か親エージェントが読む。
"""
import argparse
import re
import sys
from collections import Counter

DASH = "[──―—–]"
PROTECTED_LINES = [
    ("コメントとリンクカード", r"^\s*<!--"),
    ("図の埋め込み", r"^\[!\["),
    ("図のキャプション", r"^\*図\d+"),
    ("表の行", r"^\|"),
    ("引用", r"^>"),
    ("見出し", r"^#{1,6} "),
]


def split_front(text):
    m = re.match(r"---\n.*?\n---\n", text, flags=re.S)
    return (m.group(0), text[m.end():]) if m else ("", text)


def matching(body, pattern):
    return [line for line in body.split("\n") if re.search(pattern, line)]


def strip_markup(body):
    return re.sub(r"<!--.*?-->|<img[^>]*>|\]\([^)]*\)|^\[!\[.*$", "", body, flags=re.M)


def tail_after(body, marker):
    pos = body.find(marker)
    return None if pos < 0 else body[pos:]


def numbers(body):
    return Counter(re.findall(r"\d[\d,.]*", strip_markup(body)))


def urls(body):
    return sorted(re.findall(r"\]\(([^)\s]+)\)", body))


def compare(front0, body0, front1, body1, marker):
    ng = []
    if front0 != front1:
        ng.append("frontmatter に変更あり")
    for name, pattern in PROTECTED_LINES:
        before, after = matching(body0, pattern), matching(body1, pattern)
        if before != after:
            ng.append(f"{name}: {len(before)}行から{len(after)}行")
            ng += ["  消: " + x[:90] for x in Counter(before) - Counter(after)]
            ng += ["  増: " + x[:90] for x in Counter(after) - Counter(before)]
    if urls(body0) != urls(body1):
        ng.append("リンク差: " + str(sorted(set(urls(body0)) ^ set(urls(body1)))))
    n0, n1 = numbers(body0), numbers(body1)
    if n1 - n0:
        ng.append("増えた数値: " + str(sorted((n1 - n0).elements())))
    if n0 - n1:
        ng.append("消えた数値: " + str(sorted((n0 - n1).elements())))
    if len(re.findall(DASH, body1)) > len(re.findall(DASH, body0)):
        ng.append("ダッシュ混入: " + str(re.findall(f".{{0,10}}{DASH}.{{0,10}}", body1)[:3]))
    if marker:
        t0, t1 = tail_after(body0, marker), tail_after(body1, marker)
        if t0 is None:
            ng.append(f"--protect-after の文字列が前の版にない: {marker}")
        elif t0 != t1:
            ng.append(f"「{marker}」以降に変更あり")
    return ng


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--protect-after", default="")
    args = parser.parse_args()
    with open(args.before, encoding="utf-8") as f:
        front0, body0 = split_front(f.read())
    with open(args.after, encoding="utf-8") as f:
        front1, body1 = split_front(f.read())
    size = lambda b: len(re.sub(r"\s", "", strip_markup(b)))
    print(f"本文の字数(概算) {size(body0)} から {size(body1)}")
    ng = compare(front0, body0, front1, body1, args.protect_after)
    print("違反あり:" if ng else "違反なし")
    for line in ng:
        print(" ", line)
    sys.exit(1 if ng else 0)


if __name__ == "__main__":
    main()
