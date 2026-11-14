#!/usr/bin/env bash
# Renders the title cards and callouts in card.html to 1920x1080 PNGs with headless Edge.
# Callouts have a transparent background, to lay over the screen recording.
set -e
cd "$(dirname "$0")"
EDGE="${EDGE:-/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe}"
PAGE="file:///$(pwd -W 2>/dev/null || pwd)/card.html"
shot() {  # name, hash, extra flags
  "$EDGE" --headless=new --disable-gpu --hide-scrollbars --window-size=1920,1080 --virtual-time-budget=4000 \
    $3 --screenshot="$(pwd -W 2>/dev/null || pwd)/$1" "$PAGE#$2" 2>/dev/null
}
while IFS='=' read -r name spec; do
  [ -z "$name" ] && continue
  case "$name" in
    cards/*) shot "$name" "card|$spec" "" ;;
    callouts/*) shot "$name" "callout|$spec" "--default-background-color=00000000" ;;
  esac
done < cards.txt
echo "rendered $(ls cards | wc -l) cards and $(ls callouts | wc -l) callouts"
