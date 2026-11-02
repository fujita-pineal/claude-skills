#!/bin/bash
# 推敲ルールを取得し、確認済みの版と照合する。
# 使い方: bash fetch-rules.sh <保存先ファイル>
# 終了コード: 0 確認済みの版 / 1 取得失敗 / 2 版違い
set -u

URL=https://imoz.jp/humanizer.ja.txt
KNOWN_SHA256=752848e2eda3d58c0602c8a2e46da0c1d41a6a622af15cbf9f1e339cdef22dde
KNOWN_BYTES=64669
KNOWN_DATE=2026-11-02

out=${1:?保存先ファイルを指定してください}

code=$(curl -sSL --max-time 25 -w '%{http_code}' -o "$out" "$URL")
status=$?
if [ "$status" -ne 0 ] || [ "$code" != 200 ]; then
  echo "取得失敗: curl 終了コード ${status}、HTTP ${code}" >&2
  exit 1
fi

bytes=$(wc -c <"$out" | tr -d ' ')
sha=$(shasum -a 256 "$out" | cut -d' ' -f1)
echo "取得日 $(date +%F)、${bytes} バイト、sha256 ${sha}"

if [ "$sha" = "$KNOWN_SHA256" ]; then
  echo "確認済みの版(${KNOWN_DATE})と一致"
  exit 0
fi

echo "確認済みの版(${KNOWN_DATE}、${KNOWN_BYTES} バイト)と違います。差分を読んでから使ってください" >&2
exit 2
