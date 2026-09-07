"""njlint.sh のレポート整形。lint.py の --json 出力を stdin から受け取る。

モードごとに検出レーンを絞り、抑止した分は件数だけ示す。
抑止の理由は ../references/natural-japanese-overlay.md にある。
"""
import argparse, json, sys
from collections import Counter

# 正本が「体言止め」という語を使わないと定めているため、モードを問わず落とす。
# R1 の型 N / R / S はいずれも Pass であり、この検出器の指摘は判定に使えない。
ALWAYS_DROP = {"nominal_ending"}

# 連続した地の文の量がないと意味を成さない検出器。資料では偽陽性にしかならない。
SLIDE_DROP = {
    "low_burstiness", "low_lexical_diversity_ttr", "low_lexical_diversity_mtld",
    "low_specificity", "uniform_paragraph_structure", "antithesis_repetition",
    "repeated_sentence_lead", "low_sentence_variance", "high_length_autocorrelation",
    "paragraph_lead_conjunction", "repeated_syntax_template",
}

SEVERITY_ORDER = {"critical": 0, "warn": 1, "warning": 2, "info": 3}


def show(title, items, note=""):
    print(f"\n## {title}: {len(items)} 件{note}")
    for f in sorted(items, key=lambda x: (SEVERITY_ORDER.get(x.get("severity"), 4), x.get("line") or 0)):
        print(f"  [{(f.get('severity') or 'info').upper()}] L{f.get('line')} ({f.get('category')})")
        print(f"      {str(f.get('excerpt', '')).strip()[:78]}")
        print(f"      -> {str(f.get('detail', '')).strip()[:110]}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=["slide", "prose"])
    p.add_argument("--genre", required=True)
    p.add_argument("--target", required=True)
    args = p.parse_args()

    data = json.load(sys.stdin)
    drop = ALWAYS_DROP | (SLIDE_DROP if args.mode == "slide" else set())
    findings = data.get("findings", [])
    kept = [f for f in findings if f.get("category") not in drop]
    dropped = [f for f in findings if f.get("category") in drop]

    label = "資料" if args.mode == "slide" else "文章"
    print(f"=== njlint [{label}モード / genre={args.genre}] {args.target} ===")

    show("自然さ（要確認）", kept)
    show("読解負荷（推敲の指さし）", data.get("reading_load", {}).get("findings", []),
         "  ※ 自然さの判定には含めない")

    if dropped:
        c = Counter(f.get("category") for f in dropped)
        print(f"\n## 抑止した検出: {len(dropped)} 件")
        print("   " + " / ".join(f"{k} {v}" for k, v in c.most_common()))
        print("   理由は ../references/natural-japanese-overlay.md を参照。")

    print("\n判定は Pass / Fail ではありません。すべて要確認として扱い、直すか残すかを文脈で決めてください。")


if __name__ == "__main__":
    main()
