#!/usr/bin/env python3
"""Markdown 記事の本文を h2 節ごとに Gemini で書き換え、校閲モデル(既定は Claude の sonnet)が原文と意味照合し、
指摘を Gemini に戻して再書き換えする。指摘ゼロか --rounds 到達で確定。
usage: article_loop.py <article.md> <outdir> [--rounds 3] [--sections 2,3] [--model gemini-4-argon] [--tone standard|casual]
                       [--checker cli|agent] [--glossary terms.txt|none] [--banned words.json]
--tone casual: 原文ベースの最小書き換えで、ほんの少しだけくだけさせる(SNS の長文記事・個人ブログ向け)。frontmatter は任意。
--checker agent(既定): 照合用プロンプトを <outdir>/checks/ に書き出して終了コード 3 で止まる。
  呼び出し元の Claude Code が sonnet の subagent に照合させて JSON を置き、同じコマンドを再実行すると続きから進む。
--checker cli: 校閲コマンドで照合し、止まらずに最後まで進む(Claude Code の外から回すとき用)。
同じ outdir で再実行すると、書き出し済みの書き換えと照合結果を使って続きから進む。
出力: <outdir>/final.md(frontmatter込み)、s{NN}-r{N}.md、s{NN}-r{N}-issues.json、log.json
環境変数: GEMINI_API_KEY(必須)、GEMINI_REWRITE_MODEL、GEMINI_REWRITE_CHECKER、
REWRITE_CHECKER_CMD(--checker cli のときの校閲コマンド。既定は claude CLI)。依存ライブラリなし。"""
import argparse, hashlib, json, os, re, shlex, subprocess, sys, urllib.request, pathlib, time
from concurrent.futures import ThreadPoolExecutor

GEMINI_SYS = """あなたは日本語の技術記事の編集者です。以下の Markdown の節を、内容と順序と主張を一切変えずに、人間の書き手が書いたような自然で読みやすい日本語へ書き直してください。

必ず守ること:
- 見出し行(#で始まる行)、コードブロック(```で囲まれた範囲)、表(|で始まる行)、画像行(![で始まる行)、HTMLコメント、リンクのURLは1文字も変えない
- 数値、日付、固有名詞、ファイル名、コマンド名は変えない。新しい数値や事例、主張を足さない。削らない
- 可能性・提案・予定・傾向の言い方(「〜が考えられます」「〜の予定です」「〜しやすい」)を、断定・約束・禁止の言い方に強めない。「まだ」「毎回」「最初は」「〜だけ」のような限定の語を落とさない。文を割るときに主語や「誰に」を落とさない
- 段落の数と順序は保つ。各段落の内容を言い換えるだけにする{terms}
- 箇条書きは箇条書きのまま、項目数を変えない
- 原文にない丸括弧の補足を足さない。丸括弧の数を増やさない。中黒「・」を語の並列に使わない(読点で並べる)
- ダッシュ記号(――、—、–)、絵文字を使わない
- 「非常に」「極めて」「大幅に」「飛躍的に」「格段に」「様々な」「ソリューション」「寄り添う」「伴走」「と言えるでしょう」「ではないでしょうか」「〜していきたいと思います」「ぜひ」は使わない
- AIが「学習する」「賢くなる」「理解する」のような擬人化をしない。観測できる事実の表現にする
- 読者の感情を決めつけない(「驚くはず」「安心」など)
{tone}
- 出力は書き直した Markdown のみ。前置き・説明・コードフェンスで全体を囲むことをしない"""

TONES = {
    # 既定: 硬めの技術記事向け。原文から離れて書き直すため、くだけた原文は丁寧・硬い方向へ寄る
    # 語彙まで「引きずられない」にすると漢語が増えて硬くなり、適用時に文の分割と読点しか採用されなかった。
    # 組み立ては自由に変えさせ、語彙と文末は原文に揃えさせる。出力をそのまま採用できる形にするのが狙い
    "standard": """- 一文はおおむね60字以内。一文一義。硬い名詞句の連結(「〜の最適化の実現」など)は動詞にほどく
- 文の組み立ては原文に引きずられない。文の分割や結合、語順の入れ替え、主語と述語の組み替えをして、同じ事実と結論を読みやすく書き直す
- 語彙は原文の和語と口語を保つ。和語を漢語に置き換えない(「作る」→「作成する」、「止める」→「制限する」、「確かめる」→「確認する」、「やり方」→「手法」)。原文にない四字熟語や硬い名詞を足さない
- 文末の丁寧さと一人称は文ごとに原文のまま保つ。常体の文を「です・ます」に、「です・ます」の文を常体に変えない。「私」と「自分」を入れ替えない
- 同じ文末(「〜です。」「〜ます。」「〜ました。」など)が3文以上続く箇所は、文の組み立てを変えて続かないようにする。語尾に「のです」「んです」「のだ」を足してずらすことはしない""",
    # casual: 原文ベースの最小書き換え。standard の「引きずられない」を外さないと常体混じりが丁寧体へ戻される(実測)
    "casual": """- 硬い名詞句の連結(「〜の最適化の実現」など)は動詞にほどく
- 原文の文をベースにする。書き直しは最小限で、語尾・接続・言い回しを少し崩す程度にとどめる
- 口調: 原文より「ほんの少しだけ」カジュアルにする。書き手が自分の体験を知人に話す個人ブログの温度感
  - 原文より丁寧・硬い方向への書き換えは禁止。「作ってません」「うまくいかない」「はまった」「〜なる。」のような常体混じり・くだけた表現は、そのまま残す(「作っていません」「うまくいきません」に直さない)
  - 「自分」を「私」に変えない。「で、」「なので」「わりと」「ざっくり」などの口語もそのまま残す
  - そのうえで、1段落に0〜1か所だけ、語尾や接続をもう一段くだけさせる(例: 「〜です」→「〜なんです」「〜なんですよね」、「〜しました」→「〜してみました」、軽い「正直」「ちょっと」「けっこう」)
  - 事実や程度の主張は変えない。タメ口の連発、ネットスラング、「w」、感嘆符、絵文字は使わない""",
}

CHECK_SYS = """あなたは技術記事の校閲者です。原文と書き換え後を段落単位で突き合わせ、次の「実害のある」問題だけを列挙してください。
1. 意味の反転・条件や限定の消失・因果の入れ替わり(読者が原文と異なる事実や結論を受け取る箇所)
2. 原文にない事実・数値・例・主張が追加された箇所
3. 原文にある事実・数値・条件が落ちた箇所
4. 数値、日付、固有名詞、ファイル名、コマンド、URL の変化
5. 擬人化、誇張、読者感情の決めつけ、ダッシュ記号、禁止語(非常に/極めて/大幅に/様々な/ソリューション/ぜひ/〜と思います 等)

次は指摘しない: 語彙の言い換え、語尾やニュアンスの差、文の分割・結合、文型の変化、文体の好み。同じ事実と結論が伝わるなら問題なしとする。迷ったら書かない。

ただし次の A〜C は、語尾・助詞・副詞1語の差に見えても読者が受け取る事実が変わるため、上の除外より優先して指摘する(kind は meaning):
A. 断定の強まり: 可能性・提案・推測・予定・傾向の言い方が、実施済み・確定・約束・禁止命令の言い方に変わる(「〜する設計が考えられます」→「〜と設計します」、「来月公開の予定です」→「来月公開します」、「〜の原因になりえます」→「〜の原因です」、「〜しやすい」→「〜できます」)
B. 主体・関係の変化: 行為や判断の主体(AI、筆者、顧客、受講者など)が入れ替わる、主語が落ちて別の主体に読める、助詞の変化で所属や関係が変わる(「顧客に確認してもらうと不要だった」→「確認したところ不要だった」、「A社でツールBを使う」→「A社のツールBを使う」)
C. 限定の消失: 範囲・頻度・順序・程度・方法を絞る語(まだ、毎回、最初は、自動で、そのまま、共同で、〜だけ、〜のみ など)が落ち、主張の適用範囲が広がる

出力は JSON のみ: {"issues":[{"kind":"meaning|added|dropped|entity|style","original":"原文の該当箇所(短く引用)","rewritten":"書き換え後の該当箇所(短く引用)","note":"何が問題か1文","fact_changed":true}]}
fact_changed は、読者が受け取る事実・主張・適用範囲が原文と変わるなら true、表現の差にとどまるなら false。検討した結果「実害なし」「軽微」と判断したものは issues に入れない。
問題がなければ {"issues":[]}。"""

# 節単位の照合では記事全体の用語のずれが見えないため、先に用語集を作って Gemini と機械チェックに渡す(公開済み3本での試行から)
# 書き手の造語を入れると、言い換え禁止と出現回数の検査が違和感のある語を守ってしまう(造語が全工程を素通りした実例がある)
TERMS_SYS = """次の Markdown 記事(frontmatter を含む)から、記事全体で同じ表記に統一すべき用語を最大25語抜き出してください。
対象: 製品名・サービス名、法令・制度・規格の名称、業界で定着した専門用語、出典が定義している語。
除外: 書き手がこの記事のために作った言い方や比喩、助詞を落として詰めた複合語、単独で汎用的な語(AI、業務、記事、確認 など)、数値、URL。迷う語は入れない。
表記は記事中の表記をそのまま使う。出力は JSON のみ: {"terms":["用語1","用語2"]}"""

# subagent は同じ CHECK_SYS でも「迷ったら書かない」に強く従い、A〜C の1語差を落としやすい。
# 5節で比べると、事実が変わる指摘は claude -p 8件、subagent 9件、この補足つき subagent 13件
AGENT_CHECK_ADD = """補足(照合の進め方): 原文と書き換え後を1文ずつ対応させ、語尾・助詞・副詞・修飾語の差が A〜C に当たらないかを確かめてから判断すること。A〜C に当たるか迷ったものは省かず、fact_changed を付けて issues に入れる(fact_changed:false の指摘は書き換えに差し戻されない)。"""

# --checker agent で subagent に渡す指示文。照合の基準はプロンプトファイル側だけに置き、ここで緩めたり足したりしない
AGENT_TASK = """{prompt} を Read で読み、そのファイルに書かれた指示だけに従って作業してください。
そのファイルが求める JSON だけを Write で {result} に書き出してください。説明や前置きは JSON に含めないでください。
ほかのファイルは読まず、書かないでください。書き終えたら「done」とだけ返してください。"""

# --checker cli の校閲コマンド。stdin にプロンプトを受け取り、JSON を stdout に返せば何でもよい
CHECKER_CMD = os.environ.get("REWRITE_CHECKER_CMD", "claude -p --model sonnet --output-format text --tools \"\"")
# 書き換えで新しく入ったら差し戻す語。--banned で差し替えられる
BANNED = ["――", "—", "–", "非常に", "極めて", "大幅に", "飛躍的に", "格段に", "様々な", "ソリューション", "ぜひ", "と思います", "でしょう"]


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


def json_key(txt, key):
    """txt に含まれる JSON オブジェクトから key の配列を返す。読めなければ None。"""
    m = re.search(r"\{[\s\S]*\}", txt)
    try:
        v = json.loads(m.group(0))[key]
    except (AttributeError, ValueError, KeyError, TypeError):
        return None
    return v if isinstance(v, list) else None


def claude_json(prompt, key):
    """校閲コマンドの JSON 出力から key を返す。未ログイン等の失敗を指摘として Gemini に戻さないよう、1回再試行して駄目なら中断する。"""
    err = ""
    for _ in range(2):
        try:
            r = subprocess.run(CHECKER_CMD, shell=True, input=prompt, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            err = "timeout"; continue
        txt = r.stdout.strip()
        v = json_key(txt, key) if r.returncode == 0 else None
        if v is not None:
            return v
        err = (r.stderr.strip() or txt)[:300]
    sys.exit(f"校閲コマンドの呼び出しに失敗したため中断します(書き換えは差し戻していません): {err}")


def check_prompt(original, rewritten, checker="cli"):
    sys_ = CHECK_SYS.replace("出力は JSON のみ", AGENT_CHECK_ADD + "\n\n出力は JSON のみ") if checker == "agent" else CHECK_SYS
    return sys_ + "\n\n=== 原文 ===\n" + original + "\n\n=== 書き換え後 ===\n" + rewritten


def keep_fact_changes(issues):
    # 照合役は「実害なし」と自分で判断した項目も列挙しがちで、それを差し戻すと収束しない(実測: 25節中13節が3巡で未収束)
    return [x for x in issues if isinstance(x, dict) and x.get("fact_changed", True) is not False]


def ask(out, checker, job, prompt, key, pending):
    """照合役への問い合わせ。結果は <outdir>/checks/<job>.json に残し、再実行時はそれを使う。
    agent では結果がなければプロンプトを書き出して pending に積み、None を返す(照合なしで先へ進めない)。"""
    d = out / "checks"; d.mkdir(exist_ok=True)
    res = d / f"{job}.json"
    if res.exists():
        v = json_key(res.read_text(), key)
        if v is None:
            sys.exit(f"{res} から JSON の {key} を読めません。このファイルを消して、subagent の照合をやり直してください")
        return v
    if checker == "cli":
        v = claude_json(prompt, key)
        res.write_text(json.dumps({key: v}, ensure_ascii=False, indent=1))
        return v
    p = d / f"{job}.prompt.txt"
    p.write_text(prompt)
    pending.append((p.resolve(), res.resolve()))
    return None


def load_terms(spec, text, out, checker="cli", pending=None):
    if spec == "none":
        return []
    if spec:
        terms = [t.strip() for t in open(spec).read().split("\n") if t.strip() and not t.startswith("#")]
    else:
        v = ask(out, checker, "terms", TERMS_SYS + "\n\n=== 記事 ===\n" + text, "terms", pending)
        if v is None:
            return None
        terms = [t for t in v if isinstance(t, str) and len(t) >= 2]
    (out / "glossary.txt").write_text("\n".join(terms) + "\n")
    return terms


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


def prose(text):
    """見出し・コード・表・画像行・HTMLコメントを除いた地の文。"""
    keep = set(protected(text))
    return "\n".join(ln for ln in text.split("\n") if ln not in keep)


def kanji_ratio(text):
    j = re.findall(r"[一-龥々ぁ-んァ-ヶー]", text)
    return sum(1 for c in j if re.match(r"[一-龥々]", c)) / len(j) if j else 0.0


def kango_added(orig, new, terms=()):
    """地の文の漢字の比率が 2 ポイント以上増え、原文にない漢字2字以上の語があれば、その語を返す。閾値は記事2本の実測で決めた。"""
    po, pn = prose(orig), prose(new)
    if kanji_ratio(pn) - kanji_ratio(po) < 0.02:
        return []
    pat = r"[一-龥々]{2,}"
    old = set(re.findall(pat, po)) | {t for t in terms}
    return sorted({w for w in re.findall(pat, pn) if w not in old and not any(w in t for t in terms)})


def end_runs(text):
    """同じ文末(「。」の直前2文字)が3文以上続く箇所。段落をまたいでは数えない。各箇所の文のリストを返す。"""
    runs = []
    for para in re.split(r"\n\s*\n", prose(text)):
        sents = [s.strip() for s in re.findall(r"[^。\n]*。", para) if s.strip()]
        cur = []
        for s in sents:
            if cur and s[-3:-1] == cur[-1][-3:-1]:
                cur.append(s)
            else:
                if len(cur) >= 3:
                    runs.append(cur)
                cur = [s]
        if len(cur) >= 3:
            runs.append(cur)
    return runs


def mech_issues(orig, new, terms=()):
    iss = []
    for t in terms:
        a, b = orig.count(t), new.count(t)
        if b < a:
            iss.append({"kind": "term", "note": f"用語「{t}」が {a}回→{b}回に減った。記事全体で統一している語なので、言い換えた箇所を「{t}」に戻す"})
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
    # 全面書き直しを頼むと、丸括弧の補足と中黒の並列が増える(参照ページ12ページで実測)
    for ch, name in [("（", "丸括弧"), ("(", "丸括弧"), ("・", "中黒")]:
        if new.count(ch) > orig.count(ch):
            iss.append({"kind": "style", "note": f"{name}「{ch}」が {orig.count(ch)}個→{new.count(ch)}個に増えた。原文にない補足や並列を足さない"})
    # 漢語化は採用を止める一番の理由だった(記事7本で実測)。適用時に戻すのでなく、ループの中で直させる
    kn = kango_added(orig, new, terms)
    if kn:
        iss.append({"kind": "kango", "note": "原文にない漢語が増えて文が硬くなった。原文の和語の言い方に戻す: " + "、".join(kn[:8])})
    # 文末の反復を避けさせると「〜のです。」を足してずらす(記事1本で15片中7片)。説明口調が強まり採用できない
    for end in ["のです。", "のだ。", "なのです。"]:
        if new.count(end) > orig.count(end) + 1:
            iss.append({"kind": "style", "note": f"「{end}」が {orig.count(end)}個→{new.count(end)}個に増えた。文末をずらすために足さず、増やした文は原文の文末に戻す"})
            break
    # 文末の連続は指示だけでは減らない回がある(ある記事で 9→9、「原文より減れば可」にすると 9→8 で止まった)。原文の半分以下になるまで箇所を渡して組み替えさせる
    ro, rn = end_runs(orig), end_runs(new)
    if rn and len(rn) > len(ro) // 2:
        where = " / ".join("「" + r[0][:20] + "…」から" + str(len(r)) + "文" for r in rn[:4])
        iss.append({"kind": "style", "note": f"同じ文末が3文以上続く箇所が {len(ro)}→{len(rn)}。文を合わせるか言い切りの形を変えて続かないようにする。「のです」を足してずらさない: " + where})
    if abs(len(new) - len(orig)) > len(orig) * 0.25:
        iss.append({"kind": "length", "note": f"文字数が {len(orig)} → {len(new)} で25%以上変化"})
    return iss


def advance(i, orig, out, a, base_prompt, terms, pending):
    """1節を、書き出し済みのファイルを使いながら進められるところまで進める。照合待ちなら None。"""
    (out / f"s{i:02d}-r0-orig.md").write_text(orig)
    sec_terms = [t for t in terms if t in orig]
    sys_prompt = base_prompt.replace("{terms}", "\n- 次の語は記事全体で統一している用語。言い換えず、同じ表記のまま使う: " + "、".join(f"「{t}」" for t in sec_terms) if sec_terms else "")
    prompt = sys_prompt + "\n\n=== 節 ===\n" + orig
    cur, issues = None, []
    for r in range(1, a.rounds + 1):
        f = out / f"s{i:02d}-r{r}.md"
        if f.exists():
            cur = f.read_text()
        else:
            cur = gemini(prompt, a.model)
            cur = re.sub(r"^```(?:markdown)?\n([\s\S]*)\n```$", r"\1", cur.strip())
            f.write_text(cur)
        fi = out / f"s{i:02d}-r{r}-issues.json"
        if fi.exists():
            issues = json.loads(fi.read_text())
        else:
            checked = ask(out, a.checker, f"s{i:02d}-r{r}", check_prompt(orig, cur, a.checker), "issues", pending)
            if checked is None:
                return None
            issues = mech_issues(orig, cur, sec_terms) + keep_fact_changes(checked)
            fi.write_text(json.dumps(issues, ensure_ascii=False, indent=1))
            print(f"section {i} round {r}: {len(issues)} issues {[x['kind'] for x in issues]}", flush=True)
        if not issues:
            break
        fb = "\n".join(f"- [{x.get('kind')}] {x.get('note','')} / 原文: {x.get('original','')[:120]} / 書き換え: {x.get('rewritten','')[:120]}" for x in issues)
        # 「原文に戻す」とだけ伝えると節全体が原文へ引き戻される(実測)。直す範囲を指摘箇所に限る
        prompt = (sys_prompt + "\n\n=== 節(原文) ===\n" + orig + "\n\n=== 前回の書き換え ===\n" + cur
                  + "\n\n=== 校閲者の指摘(すべて直すこと) ===\n" + fb
                  + "\n\n前回の書き換えを土台にして、指摘された箇所だけを原文の意味に合わせて直してください。"
                  + "指摘のない文は前回の書き換えのまま変えず、原文の言い回しへ戻さないでください。直した書き換え版を出力してください。")
    (out / f"s{i:02d}-final.md").write_text(cur)
    (out / f"s{i:02d}-final-issues.json").write_text(json.dumps(issues, ensure_ascii=False, indent=1))
    return cur


def stop_for_agents(pending):
    print(f"\n照合待ち {len(pending)}件。下の指示文を1件ずつ sonnet の subagent(Agent ツール、model: sonnet)に並列で渡し、"
          "全件の JSON がそろったら同じコマンドを再実行する:\n  python3 " + " ".join(shlex.quote(x) for x in sys.argv))
    for p, res in sorted(pending):
        print("\n---\n" + AGENT_TASK.format(prompt=p, result=res))
    sys.exit(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("article"); ap.add_argument("outdir")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--sections", default="")
    ap.add_argument("--model", default=os.environ.get("GEMINI_REWRITE_MODEL", "gemini-4-argon"))
    ap.add_argument("--tone", choices=sorted(TONES), default="standard")
    ap.add_argument("--glossary", default="", help="統一する用語を1行1語で書いたファイル。省略時は校閲モデルが抽出、none で無効")
    ap.add_argument("--checker", choices=["cli", "agent"], default=os.environ.get("GEMINI_REWRITE_CHECKER", "agent"),
                    help="agent: 照合を呼び出し元の subagent に任せる(既定)。cli: 校閲コマンド(REWRITE_CHECKER_CMD、既定は claude -p)で照合")
    ap.add_argument("--banned", default="", help="禁止語リスト(JSON配列ファイル)。既定はスクリプト内の BANNED")
    a = ap.parse_args()
    if a.banned:
        BANNED[:] = json.load(open(a.banned))
    base_prompt = GEMINI_SYS.replace("{tone}", TONES[a.tone])
    out = pathlib.Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    text = open(a.article).read()
    # 続きから進めるため、別の原文や設定で作った途中結果に混ざらないようにする
    run = {"article_sha256": hashlib.sha256(text.encode()).hexdigest(), "model": a.model, "tone": a.tone, "glossary": a.glossary, "checker": a.checker}
    rf = out / "run.json"
    if rf.exists() and json.loads(rf.read_text()) != run:
        sys.exit(f"{out} には別の原文か設定で作った途中結果があります。outdir を変えるか、中身を消してから実行してください")
    rf.write_text(json.dumps(run, ensure_ascii=False, indent=1))
    m = re.match(r"^---\n[\s\S]*?\n---\n", text)
    fm, body = (m.group(0), text[m.end():]) if m else ("", text)
    pending = []
    terms = load_terms(a.glossary, text, out, a.checker, pending)
    if terms is None:
        stop_for_agents(pending)
    print(f"glossary: {terms}", flush=True)
    secs = split_sections(body)
    targets = [int(x) for x in a.sections.split(",")] if a.sections else list(range(len(secs)))
    targets = [i for i in targets if len(secs[i].strip()) >= 80]
    with ThreadPoolExecutor(4) as ex:
        done = dict(zip(targets, ex.map(lambda i: advance(i, secs[i], out, a, base_prompt, terms, pending), targets)))
    if pending:
        stop_for_agents(pending)
    final = [done.get(i) or x for i, x in enumerate(secs)]
    log = []
    for i in targets:
        for r in range(1, a.rounds + 1):
            fi = out / f"s{i:02d}-r{r}-issues.json"
            if fi.exists():
                iss = json.loads(fi.read_text())
                log.append({"section": i, "round": r, "issues": len(iss), "kinds": [x["kind"] for x in iss]})
    # Gemini は節末の空行を落とすため、次節の見出しが前段落に貼り付かないよう空行で連結する
    (out / "final.md").write_text(fm + "\n\n".join(x.rstrip("\n") for x in final) + "\n")
    (out / "log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
    print(f"完了: {out / 'final.md'}")


if __name__ == "__main__":
    main()
