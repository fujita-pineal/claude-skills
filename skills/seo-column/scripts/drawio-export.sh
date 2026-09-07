#!/usr/bin/env bash
# drawioソース → コラム本文用SVG を書き出す(パイプラインv3 Stage 4)。
#
#   scripts/drawio-export.sh <slug> <figure-no>
#   例: scripts/drawio-export.sh ad-compliance-guide 2
#     入力  docs/seo-column/figures/ad-compliance-guide/fig-2.drawio
#     出力  content/images/column/ad-compliance-guide/fig-2.svg
#
# drawio CLIのSVGエクスポートは背景が透過になる。そのままだとダークモードで
# 濃い線が濃い背景に乗って読めなくなるため、白背景の矩形を先頭に注入する。
#
# あわせて drawio 29 系が吐く CSS の light-dark() を潰す。白背景で固定した図に
# ダークモード側の淡色が乗ると線と文字が飛ぶ。--svg-theme light では消えない。
# フォントも 'Hiragino Sans' 単独で書き出されるので、フォールバック鎖に展開する。
#
# drawioソース側の作法(これを外すと文字がPNGラスタで埋め込まれて肥大化する):
#   - スタイルは html=0。html=1 だとラベルが foreignObject + base64 PNG になる
#   - whiteSpace=wrap を使わない。改行は値の中に &#10; を書く
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: $0 <slug> <figure-no>" >&2
  exit 1
fi

slug="$1"
n="$2"
src="docs/seo-column/figures/${slug}/fig-${n}.drawio"
out="content/images/column/${slug}/fig-${n}.svg"

if [ ! -f "$src" ]; then
  echo "ソースが無い: $src" >&2
  exit 1
fi

if ! command -v drawio >/dev/null 2>&1; then
  echo "drawio CLI が見つからない。brew install --cask drawio で導入する" >&2
  exit 1
fi

mkdir -p "$(dirname "$out")"
drawio --export --format svg --border 24 --output "$out" "$src" >/dev/null

python3 - "$out" <<'PY'
import re, sys

path = sys.argv[1]
svg = open(path, encoding="utf-8").read()

FONT_STACK = "'Noto Sans JP', 'Hiragino Sans', 'Yu Gothic', 'Meiryo', sans-serif"


def strip_light_dark(text):
    """light-dark(明, 暗) を明側だけに畳む。rgb(...) を含むので括弧を数える。"""
    out = []
    i = 0
    token = "light-dark("
    while True:
        j = text.find(token, i)
        if j < 0:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:j])
        k = j + len(token)
        depth, comma = 1, -1
        while k < len(text) and depth:
            c = text[k]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif c == "," and depth == 1 and comma < 0:
                comma = k
            k += 1
        inner = text[j + len(token):k - 1]
        light = text[j + len(token):comma] if comma > 0 else inner
        out.append(light.strip())
        i = k


svg = strip_light_dark(svg)
svg = svg.replace("color-scheme: light dark;", "color-scheme: light;")
svg = svg.replace("'Hiragino Sans'", FONT_STACK)

if "<foreignObject" in svg:
    sys.exit(
        f"foreignObject が残っている: {path}\n"
        "  → drawioソースの style から html=1 と whiteSpace=wrap を外す"
        "(<img>読み込み時にラベルがPNGラスタに落ちる)"
    )

# 既に注入済みなら背景処理だけ飛ばす(再エクスポート時の二重挿入を防ぐ)
if 'id="bg-white"' in svg:
    open(path, "w", encoding="utf-8").write(svg)
    print(f"背景注入済み: {path}")
    raise SystemExit(0)

m = re.search(r"<svg\b[^>]*>", svg)
if not m:
    sys.exit(f"svg要素が見つからない: {path}")

# style属性の transparent 指定を白に置き換える(<img>読み込み時の下地対策)
head = m.group(0).replace("background: transparent", "background: #ffffff") \
                 .replace("background-color: transparent", "background-color: #ffffff")

rect = '<rect id="bg-white" x="0" y="0" width="100%" height="100%" fill="#ffffff"/>'
open(path, "w", encoding="utf-8").write(svg[:m.start()] + head + rect + svg[m.end():])
print(f"白背景を注入: {path}")
PY

echo "書き出し完了: $out"
echo "→ ブラウザで開いて文字のはみ出しを目視確認すること(figure-design.md §3)"
