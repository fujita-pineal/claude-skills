#!/usr/bin/env python3
"""Gemini に平文の書き直しを依頼する。stdin に下書き、--brief に要点や口調の指示。
依存ライブラリなし。REST API を直接叩く。環境変数: GEMINI_API_KEY(必須)、GEMINI_REWRITE_MODEL、GEMINI_REWRITE_PERSONA。"""
import argparse, json, os, sys, urllib.request

COMMON = """制約: ダッシュ記号（――、—、–）を使わない。絵文字なし。
「非常に」「極めて」「大幅に」「伴走」「寄り添う」「ソリューション」は使わない。
原文にない丸括弧の補足を足さない。中黒「・」を語の並列に使わない（読点で並べる）。
和語をむやみに漢語へ置き換えない（「作る道具」→「作成ツール」のような言い換えをしない）。
出力は本文のみ。前置きや説明を付けない。"""

# {persona} は --persona で差し替える。社名の表記など書き手固有の決まりは --brief で渡す
SYSTEM = """あなたは{persona}です。下書きの内容と順序を保ったまま、人間が普段書く自然な日本語のビジネス文に書き直してください。
箇条書きは使わず文章で。
""" + COMMON

# --minimal: すでに形になっている文を渡すとき。全面書き直しを頼むと、壊れていない文まで書き換わる
MINIMAL = """あなたは日本語の校正者です。以下の文は、すでに人が書いて形になっています。
全面的な書き直しはしません。**読んで引っかかる箇所だけを直してください。**引っかからない文は1文字も変えずに返します。
直す対象: 係り受けが遠い、修飾の掛かり先が二通りに読める、「の」が3つ以上続く、一文に用件が2つ以上入って切れる、主語と述語がねじれている、言葉が足りず意味が取れない。
文末の丁寧さは行ごとに原文のまま保つ。常体の行を「です・ます」に変えない。各文を原文より長くしない。
""" + COMMON

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", default="", help="追加指示（宛先、長さ、口調など）")
    ap.add_argument("--persona", default=os.environ.get("GEMINI_REWRITE_PERSONA", "この文章の書き手本人"), help="書き手の立場(例: 〇〇社のCTO)。--minimal では使わない")
    ap.add_argument("--model", default=os.environ.get("GEMINI_REWRITE_MODEL", "gemini-4-argon"))
    ap.add_argument("--minimal", action="store_true", help="全面書き直しでなく、引っかかる箇所だけを直す")
    a = ap.parse_args()
    draft = sys.stdin.read()
    key = os.environ.get("GEMINI_API_KEY") or sys.exit("GEMINI_API_KEY が未設定")
    prompt = (MINIMAL if a.minimal else SYSTEM.replace("{persona}", a.persona)) +("\n\n追加指示: " + a.brief if a.brief else "") + "\n\n---下書き---\n" + draft
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{a.model}:generateContent?key={key}"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    r = urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json"}), timeout=120)
    print(json.load(r)["candidates"][0]["content"]["parts"][0]["text"].strip())

if __name__ == "__main__":
    main()
