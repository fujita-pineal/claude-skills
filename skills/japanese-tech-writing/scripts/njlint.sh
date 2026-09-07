#!/usr/bin/env bash
# njlint.sh — 成果物タイプに合わせて lint.py の検出レーンを切り替えるラッパー。
#
#   njlint.sh --mode slide <file>              資料（スライド、提案書、Slack投稿、xlsx のセル）
#   njlint.sh --mode prose [--genre X] <file>  文章（記事、レポート、議事録、note）
#
# 資料は断片テキストの集合なので、文書統計の検出器は意味を成さず偽陽性しか出ません。
# 文単位で決定的に効く検出器と、読解負荷レーンだけを残します。
#
# findings は Fail ではなく「要確認」です。直すか残すかは文脈で判断してください。
# 判定の正本は ~/.claude/rules/document-tone-rules.md と、このスキルの SKILL.md です。
# ベンダリング元と、正本による打ち消しは UPSTREAM.md と
# ../references/natural-japanese-overlay.md を参照してください。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="" ; GENRE="" ; FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)  MODE="${2:-}"  ; shift 2 ;;
    --genre) GENRE="${2:-}" ; shift 2 ;;
    -h|--help) sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ; exit 0 ;;
    -*) echo "不明なオプション: $1" >&2 ; exit 1 ;;
    *)  FILE="$1" ; shift ;;
  esac
done

[[ -n "$FILE" ]] || { echo "対象ファイルを指定してください。--help で使い方を表示します。" >&2 ; exit 1 ; }
[[ -f "$FILE" ]] || { echo "ファイルが見つかりません: $FILE" >&2 ; exit 1 ; }

case "$MODE" in
  slide) GENRE="${GENRE:-business}" ;;
  prose) GENRE="${GENRE:-essay}" ;;
  *) echo "--mode に slide か prose を指定してください。" >&2 ; exit 1 ;;
esac

uv run --quiet "$HERE/lint.py" --genre "$GENRE" --json --reading-load "$FILE" \
  | python3 "$HERE/njlint_report.py" --mode "$MODE" --genre "$GENRE" --target "$FILE"
