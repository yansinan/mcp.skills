#!/usr/bin/env bash
# ncm-player — 网易云音乐 waybar 调度器模板
# 安装到 ~/.local/bin/ncm-player，chmod +x
# waybar 配置中所有按钮调用此脚本，不直接调用 ncm/ncm-cli
#
# 依赖:
#   ncm-cli (npm) — 播放控制
#   ncm (Go)     — 数据操作（搜索/歌单/推荐）
#   mpv-mpris    — D-Bus MPRIS 显示

set -euo pipefail

NCM_CLI="ncm-cli"
NCM_GO="$HOME/.local/bin/ncm"
STATE_DIR="$HOME/.local/share/ncmctl"
STATE_FILE="$STATE_DIR/state.json"
mkdir -p "$STATE_DIR"

check_login() {
  $NCM_CLI login --check 2>&1 | grep -q '"success": true'
}

case "${1:-help}" in
  # waybar 按钮输出
  status-button)
    if check_login; then printf '\U0000F00C'; else printf '\U0000F09C'; fi ;;
  play-button)
    state=$($NCM_CLI state 2>/dev/null | python3 -c "
import sys,json
try: print(json.load(sys.stdin).get('state',{}).get('status','stopped'))
except: print('stopped')")
    [ "$state" = "playing" ] && printf '\U0000F04C' || printf '\U0000F04B' ;;
  like-button)   printf '\U00002661' ;;
  prev-button)   printf '\U0000F048' ;;
  next-button)   printf '\U0000F051' ;;
  playlist-button)
    if check_login; then printf '\U0001F3B5'; fi ;;
  logged_only)
    if check_login; then printf '%s' "${2:-}"; fi ;;

  # 播放控制
  toggle)
    state=$($NCM_CLI state 2>/dev/null | python3 -c "
import sys,json
try: print(json.load(sys.stdin).get('state',{}).get('status','stopped'))
except: print('stopped')")
    [ "$state" = "playing" ] && $NCM_CLI pause >/dev/null 2>&1 || $NCM_CLI resume >/dev/null 2>&1 || true ;;
  next)  $NCM_CLI next >/dev/null 2>&1 || true ;;
  prev)  $NCM_CLI prev >/dev/null 2>&1 || true ;;
  volume) $NCM_CLI volume "${2:-50}" >/dev/null 2>&1 || true ;;

  # 登录
  login)
    QR_OUT=$(mktemp)
    $NCM_CLI login --background --output json 2>/dev/null > "$QR_OUT" || { notify-send "网易云" "登录失败" -i dialog-error -t 3000; rm -f "$QR_OUT"; exit 1; }
    qr_url=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('clickableUrl') or d.get('qrCodeUrl',''))" "$QR_OUT" 2>/dev/null)
    rm -f "$QR_OUT"
    [ -z "$qr_url" ] && { notify-send "网易云" "获取二维码失败" -i dialog-error -t 3000; exit 1; }
    png="$STATE_DIR/qr.png"
    qrencode -o "$png" -s 10 -m 2 "$qr_url" 2>/dev/null || true
    qrencode -o - -t UTF8 -s 1 -m 2 "$qr_url" 2>/dev/null || true
    printf "\n扫码登录: %s\n" "$qr_url"
    for i in $(seq 90); do sleep 2; check_login && { notify-send "网易云" "登录成功 ✓" -i dialog-information -t 3000; exit 0; }; printf "." >&2; done
    notify-send "网易云" "登录超时" -i dialog-error -t 3000 ;;

  # 歌单 / 推荐 / 搜索（需 Go 二进制）
  pl) exec "$(dirname "$0")/ncm-playlist" ;;
  fm|recommend)
    [ ! -x "$NCM_GO" ] && { notify-send "网易云" "需要 ncm Go 二进制" -i dialog-error -t 5000; exit 1; }
    songs=$("$NCM_GO" recommend songs --json 2>/dev/null) || { notify-send "网易云" "获取推荐失败" -i dialog-error -t 3000; exit 1; }
    first_id=$(echo "$songs" | python3 -c "import json,sys; d=json.load(sys.stdin); items=d.get('data',d.get('songs',d.get('recommend',[]))) or d.get('result',[]); print(items[0].get('id','') if items else '')" 2>/dev/null)
    [ -n "$first_id" ] && $NCM_CLI play --song --encrypted-id "$first_id" --output json >/dev/null 2>&1 ;;
  search)
    [ ! -x "$NCM_GO" ] && { echo "需要 ncm Go 二进制"; exit 1; }
    keyword="${2:-}"; [ -z "$keyword" ] && { echo "用法: ncm search <关键词>"; exit 1; }
    "$NCM_GO" search song "$keyword" --json ;;

  like) notify-send "网易云" "红心暂不支持" -i dialog-information -t 3000 ;;
  info)
    echo "=== login ==="; check_login && echo "✓ 已登录" || echo "✗ 未登录"
    echo "=== ncm-cli state ==="; $NCM_CLI state --output human 2>&1
    echo "=== mpv ==="; pgrep -a mpv 2>/dev/null || echo "(mpv 未运行)"
    echo "=== ncm ==="; [ -x "$NCM_GO" ] && echo "✓ $($NCM_GO version 2>&1)" || echo "✗ 未安装" ;;
  state) $NCM_CLI state 2>/dev/null || echo '{}' ;;
  help|--help|-h)
    cat <<'USAGE'
ncm-player — 网易云音乐调度器
播放控制: toggle / next / prev / volume / login
数据操作: fm / search / pl (需 Go 二进制)
Waybar:   status-button / play-button / like-button / prev-button / next-button
调试:     info / state
USAGE ;;
  *) echo "未知子命令: $1（用 'help' 看用法）" >&2; exit 1 ;;
esac
