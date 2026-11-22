#!/usr/bin/env python3
"""HTML 断片(参照ページ)を Gemini に最小改稿させる。タグ・数値・リンク・文体を機械検査し、
違反が出たらその箇所だけを直させる差し戻しを回す。

usage:
  html_rewrite.py <pages ディレクトリ か .html ファイル> <outdir> [--files a.html,b.html]
                  [--model gemini-4-argon] [--rounds 2] [--brief "このサイトの事情"]

全面書き直しは頼まない。「読んで引っかかる箇所だけ直す。引っかからない文は1文字も変えない」で指示する。
記事モード(article_loop.py)と違い、照合役のモデルは使わない。断片が短く、機械検査で足りるため。
環境変数: GEMINI_API_KEY(必須)、GEMINI_REWRITE_MODEL。依存ライブラリなし。"""
import argparse, json, os, pathlib, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

SYS = """あなたは日本語の技術文書の校正者です。以下は参照ページの1ページ分の HTML 断片です。
これは読み物ではなく、必要なときに引く参照ページです。短い常体の箇条書きと表で作ってあります。

やることは全面的な書き直しではありません。**読んで引っかかる箇所だけを直してください。**
引っかからない文は1文字も変えずにそのまま返します。直すのは次に当たる箇所だけです。

直す対象:
- 係り受けが遠い、修飾の掛かり先が二通りに読める
- 「の」が3つ以上続く、同じ助詞が続いて読みにくい
- 倒置や名詞止めのせいで、何が主語か一読で分からない
- 一文に用件が2つ以上入っていて切れる
- 主語と述語がねじれている
- 言葉が足りず、意味が取れない

絶対に変えないもの:
- HTML のタグ。種類、属性、数、並び順、入れ子をそのまま保つ。足さない、消さない、入れ替えない
- <pre>、<code> の中身。コマンド、ファイル名、パス、スキル名、URL
- 箇条書きの項目数、表のセルの数、見出しの意味
- 数値、日付、固有名詞。新しい事実・例・主張を足さない。削らない

文体の制約（破ったら不採用になります）:
- 文末の丁寧さを、行ごとに原文のまま保つ。原文が常体（「〜する」「〜しない」「〜になる」）や体言止めの行を、「です・ます」に変えない。原文が敬体の行は敬体のまま
- 原文にない丸括弧の補足を足さない。丸括弧の数を増やさない
- 和語を漢語に置き換えない。「作る道具」を「作成ツール」に、「止める」を「制限する」に、「照らす」を「照合する」に、「失くす」を「紛失する」にしない。原文の語を優先し、語彙の言い換えは意味が取れないときだけ
- 中黒「・」を語の並列に使わない。読点で並べる
- 対になった短い言い回し（「集計はコード、解釈は Claude」など）の形を崩さない
- 具体的な指示を抽象化しない。「読ませない側に書く」を「読ませない設定にする」のようにぼかさない
- 各項目を原文より長くしない。説明を足さない
- ダッシュ記号（――、—、–）、絵文字を使わない
- 「非常に」「極めて」「大幅に」「飛躍的に」「格段に」「様々な」「ソリューション」「寄り添う」「伴走」「と言えるでしょう」「ではないでしょうか」「〜していきたいと思います」「ぜひ」は使わない
- AI が「学習する」「賢くなる」「理解する」のような擬人化をしない
- 読者の感情を決めつけない（「驚くはず」「安心」など）
- 可能性・提案の言い方を、断定・約束・禁止に強めない。「ことがある」「だけ」「まず」のような限定の語を落とさない

出力は直したあとの HTML のみ。前置き・説明・コードフェンスで全体を囲むことをしない。"""

TAG = re.compile(r"<[^>]+>")
NUM = re.compile(r"\d+")
PRE = re.compile(r"<(pre|code)>(.*?)</\1>", re.S)
POLITE = re.compile(r"(です|ます|ません|ましょう|でしょう)(。|、|$|</)")
BAD = ("非常に", "極めて", "大幅に", "飛躍的に", "格段に", "様々な", "ソリューション",
       "寄り添", "伴走", "ぜひ", "——", "—", "–")


def key():
    return os.environ.get("GEMINI_API_KEY") or sys.exit("GEMINI_API_KEY が未設定")


def gemini(prompt, k, model):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={k}"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    r = urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json"}), timeout=300)
    out = json.load(r)["candidates"][0]["content"]["parts"][0]["text"].strip()
    return re.sub(r"\n```$", "", re.sub(r"^```(?:html)?\n", "", out))


def segs(s):
    """タグを境にしたテキスト片の列。タグ列が一致していれば片の数も一致する。"""
    return [x.strip() for x in TAG.split(s)]


def checks(a, b):
    """(指摘のリスト, 変更量の表示) を返す。タグ列が壊れていたら他を見ずに返す。"""
    ta, tb = TAG.findall(a), TAG.findall(b)
    if ta != tb:
        d = [(i, x, y) for i, (x, y) in enumerate(zip(ta, tb)) if x != y][:3]
        return [f"タグ列がちがう ({len(ta)}→{len(tb)}) {d}"], ""
    bad = []
    if PRE.findall(a) != PRE.findall(b):
        bad.append("pre/code の中身がちがう")
    if sorted(NUM.findall(a)) != sorted(NUM.findall(b)):
        bad.append(f"数値がちがう ({len(NUM.findall(a))}→{len(NUM.findall(b))}個) "
                   f"{sorted(set(NUM.findall(a)) ^ set(NUM.findall(b)))}")
    if sorted(re.findall(r'href="([^"]+)"', a)) != sorted(re.findall(r'href="([^"]+)"', b)):
        bad.append("リンク先がちがう")
    for w in BAD:
        if w in b and w not in a:
            bad.append(f"禁止語 {w}")
    sa, sb = segs(a), segs(b)
    for x, y in zip(sa, sb):
        if x == y or not x:
            continue
        if not POLITE.search(x) and POLITE.search(y):
            bad.append(f"常体→敬体: 「{x[:28]}」→「{y[:28]}」")
        if y.count("（") + y.count("(") > x.count("（") + x.count("("):
            bad.append(f"丸括弧が増えた: 「{y[:36]}」")
        if y.count("・") > x.count("・"):
            bad.append(f"中黒が増えた: 「{y[:36]}」")
        if len(y) > len(x) * 1.2 + 4:
            bad.append(f"長くなった ({len(x)}→{len(y)}): 「{y[:36]}」")
    if not (0.85 <= len(b) / len(a) <= 1.15):
        bad.append(f"全体の字数が {len(a)}→{len(b)} ({len(b)/len(a):.2f}倍)")
    changed = sum(1 for x, y in zip(sa, sb) if x != y and x)
    return bad, f"{changed}/{sum(1 for x in sa if x)}片を変更"


def run(p, outdir, k, a, sys_prompt):
    src = p.read_text(encoding="utf-8")
    new = gemini(sys_prompt + "\n\n---原文---\n" + src, k, a.model)
    bad, info = checks(src, new)
    for _ in range(a.rounds):
        if not bad:
            break
        # 「全部やり直す」と言うと別物が返る。直す範囲を指摘箇所に限る
        fix = (sys_prompt + "\n\n以下の書き換え結果に、守れていない点があります。"
               "**指摘された箇所だけ**を直し、それ以外は書き換え結果のまま返してください。\n\n指摘:\n"
               + "\n".join("- " + x for x in bad)
               + "\n\n---原文---\n" + src + "\n\n---書き換え結果---\n" + new)
        new = gemini(fix, k, a.model)
        bad, info = checks(src, new)
    (outdir / p.name).write_text(new + ("" if new.endswith("\n") else "\n"), encoding="utf-8")
    return p.name, bad, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="pages ディレクトリ、または .html ファイル1つ")
    ap.add_argument("outdir")
    ap.add_argument("--files", default="", help="ディレクトリ指定のとき、処理するファイル名をカンマ区切りで絞る")
    ap.add_argument("--model", default=os.environ.get("GEMINI_REWRITE_MODEL", "gemini-4-argon"))
    ap.add_argument("--rounds", type=int, default=2, help="指摘が出たときの差し戻し回数の上限")
    ap.add_argument("--brief", default="", help="このサイト固有の事情を1〜2行で足す")
    a = ap.parse_args()
    src = pathlib.Path(a.src)
    files = [src] if src.is_file() else sorted(src.glob("*.html"))
    if a.files:
        want = set(a.files.split(","))
        files = [f for f in files if f.name in want]
    if not files:
        sys.exit(f"{a.src} に対象の .html がない")
    outdir = pathlib.Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    sys_prompt = SYS + ("\n\n補足: " + a.brief if a.brief else "")
    k = key()
    ng = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for name, bad, info in ex.map(lambda p: run(p, outdir, k, a, sys_prompt), files):
            ng += bool(bad)
            print(f"{name}: {info} " + ("OK" if not bad else "NG " + " / ".join(bad[:4])), flush=True)
    print(f"\n書き出し: {outdir}  （NG {ng}/{len(files)}）")


if __name__ == "__main__":
    main()
