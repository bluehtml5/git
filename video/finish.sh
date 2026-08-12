#!/usr/bin/env bash
# 把錄好的 demo 轉成 mp4，並接上 CUBE 正式片尾。
#
#   ./video/finish.sh video/out/page@xxxx.webm assets/cube-outro.mp4 [輸出.mp4]
#
# 需要系統的 ffmpeg（Playwright 內建那顆是精簡版，沒有 libx264，不能用）。
set -euo pipefail

DEMO=${1:?用法: finish.sh <demo.webm> <outro.mp4> [輸出.mp4]}
OUTRO=${2:?缺少片尾檔}
OUT=${3:-video/out/final.mp4}
FF=${FFMPEG:-ffmpeg}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# 兩段都正規化成 1080x1920 / 30fps / 有音軌，否則 concat 會對不上。
# demo 沒有聲音，補一條無聲軌，這樣接上片尾後片尾的聲音才不會被丟掉。
norm () {
  local src=$1 dst=$2 extra=${3:-}
  # shellcheck disable=SC2086
  $FF -loglevel error -y $extra -i "$src" \
    -f lavfi -t 9999 -i anullsrc=channel_layout=stereo:sample_rate=44100 \
    -shortest -map 0:v:0 -map 1:a:0 \
    -vf "scale=1080:1920:force_original_aspect_ratio=decrease,\
pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x0c0d10,fps=30,format=yuv420p" \
    -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k -ar 44100 "$dst"
}

echo "→ 正規化 demo"
norm "$DEMO" "$TMP/a.mp4"

echo "→ 正規化片尾"
if $FF -loglevel error -i "$OUTRO" -map 0:a:0 -t 0.1 -f null - 2>/dev/null; then
  # 片尾本身有聲音，保留它
  $FF -loglevel error -y -i "$OUTRO" \
    -vf "scale=1080:1920:force_original_aspect_ratio=decrease,\
pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x0c0d10,fps=30,format=yuv420p" \
    -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k -ar 44100 -ac 2 "$TMP/b.mp4"
else
  norm "$OUTRO" "$TMP/b.mp4"
fi

echo "→ 接起來"
printf "file '%s'\nfile '%s'\n" "$TMP/a.mp4" "$TMP/b.mp4" > "$TMP/list.txt"
mkdir -p "$(dirname "$OUT")"
$FF -loglevel error -y -f concat -safe 0 -i "$TMP/list.txt" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -movflags +faststart "$OUT"

echo "完成：$OUT"
$FF -hide_banner -i "$OUT" 2>&1 | grep -E "Duration|Stream"
