"""njlint.sh のレポート整形。lint.py の --json 出力を stdin から受け取る。

モードごとに検出レーンを絞り、抑止した分は件数だけ示す。
同じ対象に yomiyasu_lint.py も掛け、比喩動詞と定型句の指摘を別の節に出す。
抑止の理由は ../references/natural-japanese-overlay.md と ../references/yomiyasu-overlay.md にある。
"""
import argparse, json, sys
from collections import Counter
from pathlib import Path

import yomiyasu_lint  # 無改変のベンダリング。出所は UPSTREAM.md

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

# yomiyasu_lint.py の検出のうち、正本と衝突するものと lint.py と重複するもの。
Y_ALWAYS_DROP = {
    "unnatural_halfwidth_space",  # 和欧文のあいだに半角空白を入れる表記と逆
    "excess_list",                # ネスト箇条書きを基本とする規範と衝突。lint.py の high_bullet_ratio と重複
    "excess_bold",                # lint.py の high_bold_density と重複
    "trailing_colon",             # 列挙・例示の前のコロンは可とする規範と衝突
}
# 断片テキストの集合では文末の連続が成り立たない。
Y_SLIDE_DROP = {"sentence_end_repetition"}
# 運用側の規約語。語を名指しする検出（slop_vocabulary、calque、translated_term）のうち、この語の指摘だけを落とす。
Y_DROP_WORDS = {"正本", "台帳", "版"}
Y_WORD_RULES = {"slop_vocabulary", "calque", "translated_term"}


def _names_drop_word(message):
    """message が Y_DROP_WORDS の語を名指ししているか。書き方は規則ごとに違う。"""
    return any(f"「{w}」" in message or f"当たった言い方: {w}）" in message for w in Y_DROP_WORDS)

SEVERITY_ORDER = {"error": 0, "critical": 0, "warn": 1, "warning": 2, "info": 3}


def show(title, items, note=""):
    print(f"\n## {title}: {len(items)} 件{note}")
    for f in sorted(items, key=lambda x: (SEVERITY_ORDER.get(x.get("severity"), 4), x.get("line") or 0)):
        print(f"  [{(f.get('severity') or 'info').upper()}] L{f.get('line')} ({f.get('category')})")
        print(f"      {str(f.get('excerpt', '')).strip()[:78]}")
        print(f"      -> {str(f.get('detail', '')).strip()[:110]}")


def yomiyasu_findings(target, mode):
    """yomiyasu_lint の findings を lint.py と同じキーに揃え、(残す, 落とす) に分ける。"""
    result = yomiyasu_lint.lint_text(Path(target).read_text(encoding="utf-8"))
    drop = Y_ALWAYS_DROP | (Y_SLIDE_DROP if mode == "slide" else set())
    kept, dropped = [], []
    for r in result["findings"]:
        f = {"category": r["rule"], "line": r["line"], "severity": r["severity"],
             "excerpt": r["snippet"], "detail": r["message"]}
        word_hit = r["rule"] in Y_WORD_RULES and _names_drop_word(r["message"])
        (dropped if r["rule"] in drop or word_hit else kept).append(f)
    return kept, dropped


def report_dropped(items, overlay):
    if not items:
        return
    c = Counter(f.get("category") for f in items)
    print("   " + " / ".join(f"{k} {v}" for k, v in c.most_common()) + f"（理由は ../references/{overlay}）")


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

    try:
        y_kept, y_dropped = yomiyasu_findings(args.target, args.mode)
        show("比喩動詞と定型句（yomiyasu、要確認）", y_kept)
    except Exception as e:  # yomiyasu 側の失敗で lint.py の結果まで失わないようにする
        y_dropped = []
        print(f"\n## 比喩動詞と定型句（yomiyasu）: 実行できませんでした（{e}）")

    if dropped or y_dropped:
        print(f"\n## 抑止した検出: {len(dropped) + len(y_dropped)} 件")
        report_dropped(dropped, "natural-japanese-overlay.md")
        report_dropped(y_dropped, "yomiyasu-overlay.md")

    print("\n判定は Pass / Fail ではありません。すべて要確認として扱い、直すか残すかを文脈で決めてください。")


if __name__ == "__main__":
    main()
