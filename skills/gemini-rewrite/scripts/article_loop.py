#!/usr/bin/env python3
"""Markdown 記事の本文を h2 節ごとに Gemini で書き換え、Claude(sonnet) が原文と意味照合し、
指摘を Gemini に戻して再書き換えする。指摘ゼロか --rounds 到達で確定。
usage: article_loop.py <article.md> <outdir> [--rounds 3] [--sections 2,3] [--model gemini-3.8-flash]
出力: <outdir>/final.md(frontmatter込み)、s{NN}-r{N}.md、s{NN}-r{N}-issues.json、log.json
環境変数: GEMINI_API_KEY(必須)、GEMINI_REWRITE_MODEL、REWRITE_CHECKER_CMD(校閲コマンド。既定は claude CLI)。"""
import argparse, json, os, re, subprocess, sys, urllib.request, pathlib, time

GEMINI_SYS = """あなたは日本語の技術記事の編集者です。以下の Markdown の節を、内容と順序と主張を一切変えずに、人間の書き手が書いたような自然で読みやすい日本語へ書き直してください。

必ず守ること:
- 見出し行(#で始まる行)、コードブロック(```で囲まれた範囲)、表(|で始まる行)、画像行(![で始まる行)、HTMLコメント、リンクのURLは1文字も変えない
- 数値、日付、固有名詞、ファイル名、コマンド名は変えない。新しい数値や事例、主張を足さない。削らない
- 段落の数と順序は保つ。各段落の内容を言い換えるだけにする
- 箇条書きは箇条書きのまま、項目数を変えない
- ダッシュ記号(――、—、–)、絵文字を使わない
- 「非常に」「極めて」「大幅に」「飛躍的に」「格段に」「様々な」「ソリューション」「寄り添う」「伴走」「と言えるでしょう」「ではないでしょうか」「〜していきたいと思います」「ぜひ」は使わない
- AIが「学習する」「賢くなる」「理解する」のような擬人化をしない。観測できる事実の表現にする
- 読者の感情を決めつけない(「驚くはず」「安心」など)
- 一文はおおむね60字以内。一文一義。硬い名詞句の連結(「〜の最適化の実現」など)は動詞にほどく
- 原文の語彙や文型に引きずられない。同じ事実と結論を、自分の言葉で書き直す。文の分割や結合、語順の入れ替えはしてよい
- 出力は書き直した Markdown のみ。前置き・説明・コードフェンスで全体を囲むことをしない"""

CHECK_SYS = """あなたは技術記事の校閲者です。原文と書き換え後を段落単位で突き合わせ、次の「実害のある」問題だけを列挙してください。
1. 意味の反転・条件や限定の消失・因果の入れ替わり(読者が原文と異なる事実や結論を受け取る箇所)
2. 原文にない事実・数値・例・主張が追加された箇所
3. 原文にある事実・数値・条件が落ちた箇所
4. 数値、日付、固有名詞、ファイル名、コマンド、URL の変化
5. 擬人化、誇張、読者感情の決めつけ、ダッシュ記号、禁止語(非常に/極めて/大幅に/様々な/ソリューション/ぜひ/〜と思います 等)

次は指摘しない: 語彙の言い換え、語尾やニュアンスの差、文の分割・結合、文型の変化、文体の好み。同じ事実と結論が伝わるなら問題なしとする。迷ったら書かない。

出力は JSON のみ: {"issues":[{"kind":"meaning|added|dropped|entity|style","original":"原文の該当箇所(短く引用)","rewritten":"書き換え後の該当箇所(短く引用)","note":"何が問題か1文"}]}
問題がなければ {"issues":[]}。"""


def gemini(prompt, model):
    key = os.environ.get("GEMINI_API_KEY") or sys.exit("GEMINI_API_KEY が未設定")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.4}}).encode()
    for i in range(3):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json"}), timeout=180)
            return json.load(r)["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            if i == 2:
                raise
            time.sleep(5)


CHECKER_CMD = os.environ.get("REWRITE_CHECKER_CMD", "claude -p --model sonnet --output-format text --tools \"\"")
BANNED = ["――", "—", "–", "非常に", "極めて", "大幅に", "飛躍的に", "格段に", "様々な", "ソリューション", "ぜひ", "と思います", "でしょう"]


def claude_check(original, rewritten):
    """校閲コマンドは stdin にプロンプトを受け取り、JSON を stdout に返せば何でもよい。"""
    prompt = CHECK_SYS + "\n\n=== 原文 ===\n" + original + "\n\n=== 書き換え後 ===\n" + rewritten
    r = subprocess.run(CHECKER_CMD, shell=True, input=prompt, capture_output=True, text=True, timeout=600)
    txt = r.stdout.strip()
    m = re.search(r"\{[\s\S]*\}", txt)
    try:
        return json.loads(m.group(0))["issues"] if m else [{"kind": "parse", "note": txt[:300]}]
    except Exception:
        return [{"kind": "parse", "note": txt[:300]}]


def split_sections(body):
    """コードフェンス外の h2 で分割。先頭(導入)は section 0。"""
    lines = body.split("\n")
    secs, cur, fence = [], [], False
    for ln in lines:
        if ln.startswith("```"):
            fence = not fence
        if not fence and ln.startswith("## ") and cur:
            secs.append("\n".join(cur)); cur = []
        cur.append(ln)
    secs.append("\n".join(cur))
    return secs


def protected(text):
    """変更禁止部分を抽出(検証用)。"""
    out, fence = [], False
    for ln in text.split("\n"):
        if ln.startswith("```"):
            fence = not fence; out.append(ln); continue
        if fence or ln.startswith("#") or ln.startswith("|") or ln.startswith("![") or ln.startswith("<!--"):
            out.append(ln)
    return out


def mech_issues(orig, new):
    iss = []
    po, pn = protected(orig), protected(new)
    if po != pn:
        iss.append({"kind": "protected", "note": "見出し・コード・表・画像行のいずれかが変わっている", "original": "\n".join(po)[:400], "rewritten": "\n".join(pn)[:400]})
    for pat, name in [(r"\d[\d,\.]*", "数値"), (r"\]\(([^)]+)\)", "リンクURL")]:
        a, b = sorted(re.findall(pat, orig)), sorted(re.findall(pat, new))
        if a != b:
            iss.append({"kind": "entity", "note": f"{name}の集合が一致しない", "original": ",".join(sorted(set(a) - set(b)))[:200], "rewritten": ",".join(sorted(set(b) - set(a)))[:200]})
    hit = [w for w in BANNED if w in new and w not in orig]
    if hit:
        iss.append({"kind": "style", "note": "禁止語: " + ",".join(hit)})
    if abs(len(new) - len(orig)) > len(orig) * 0.25:
        iss.append({"kind": "length", "note": f"文字数が {len(orig)} → {len(new)} で25%以上変化"})
    return iss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("article"); ap.add_argument("outdir")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--sections", default="")
    ap.add_argument("--model", default=os.environ.get("GEMINI_REWRITE_MODEL", "gemini-3.8-flash"))
    ap.add_argument("--banned", default="", help="禁止語リスト(JSON配列ファイル)。既定はスクリプト内の BANNED")
    a = ap.parse_args()
    if a.banned:
        BANNED[:] = json.load(open(a.banned))
    out = pathlib.Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    text = open(a.article).read()
    m = re.match(r"^---\n[\s\S]*?\n---\n", text)
    fm, body = m.group(0), text[m.end():]
    secs = split_sections(body)
    targets = [int(x) for x in a.sections.split(",")] if a.sections else list(range(len(secs)))
    final = list(secs)
    log = []
    for i in targets:
        orig = secs[i]
        if len(orig.strip()) < 80:
            continue
        (out / f"s{i:02d}-r0-orig.md").write_text(orig)
        prompt = GEMINI_SYS + "\n\n=== 節 ===\n" + orig
        cur, issues = None, []
        for r in range(1, a.rounds + 1):
            cur = gemini(prompt, a.model)
            cur = re.sub(r"^```(?:markdown)?\n([\s\S]*)\n```$", r"\1", cur.strip())
            (out / f"s{i:02d}-r{r}.md").write_text(cur)
            issues = mech_issues(orig, cur) + claude_check(orig, cur)
            (out / f"s{i:02d}-r{r}-issues.json").write_text(json.dumps(issues, ensure_ascii=False, indent=1))
            log.append({"section": i, "round": r, "issues": len(issues), "kinds": [x["kind"] for x in issues]})
            print(f"section {i} round {r}: {len(issues)} issues {[x['kind'] for x in issues]}", flush=True)
            if not issues:
                break
            fb = "\n".join(f"- [{x.get('kind')}] {x.get('note','')} / 原文: {x.get('original','')[:120]} / 書き換え: {x.get('rewritten','')[:120]}" for x in issues)
            prompt = (GEMINI_SYS + "\n\n=== 節(原文) ===\n" + orig + "\n\n=== 前回の書き換え ===\n" + cur
                      + "\n\n=== 校閲者の指摘(すべて直すこと。原文の意味と情報量に戻す) ===\n" + fb
                      + "\n\n指摘を直した書き換え版を出力してください。")
        final[i] = cur
        (out / f"s{i:02d}-final.md").write_text(cur)
        (out / f"s{i:02d}-final-issues.json").write_text(json.dumps(issues, ensure_ascii=False, indent=1))
    (out / "final.md").write_text(fm + "\n".join(final))
    (out / "log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
