#!/usr/bin/env bash
# verify.sh — 验证 mpv + waybar + sway 集成是否正常
# 用法: bash verify.sh
# 返回 0 = 全部通过，非 0 = 某个环节失败
set -e

PASS=0
FAIL=0
WARN=0

pass() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }
warn() { echo "  ! $1"; WARN=$((WARN+1)); }

# 1. 检查包
echo "═══ 1. 必需包检查 ═══"
for pkg in mpv playerctl; do
    if command -v $pkg >/dev/null 2>&1; then
        pass "$pkg 已装"
    else
        fail "$pkg 未装 (apt install $pkg)"
    fi
done

# mpv-mpris 单独检查
if dpkg -l mpv-mpris 2>/dev/null | grep -q "^ii"; then
    pass "mpv-mpris 已装"
else
    fail "mpv-mpris 未装 (apt install mpv-mpris — 不在 mpv 包里)"
fi

# 2. 检查 mpv 进程
echo
echo "═══ 2. mpv 进程检查 ═══"
MPV_PID=$(pgrep -x mpv | head -1)
if [ -n "$MPV_PID" ]; then
    pass "mpv 在跑 (PID $MPV_PID)"
    if grep -q "input-ipc-server" /proc/$MPV_PID/cmdline 2>/dev/null; then
        pass "mpv 用了 IPC socket"
    else
        warn "mpv 没看到 input-ipc-server，可能没用 IPC 启动"
    fi
else
    warn "mpv 没运行（headless 是正常的，没歌时 idle）"
fi

# 3. 检查 IPC socket
echo
echo "═══ 3. IPC socket 检查 ═══"
IPC_PATH="/tmp/ncm-mpv.sock"
if [ -S "$IPC_PATH" ]; then
    pass "$IPC_PATH 存在"
    if python3 -c "
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect('$IPC_PATH')
    s.close()
    exit(0)
except: exit(1)
" 2>/dev/null; then
        pass "IPC socket 可连"
    else
        fail "IPC socket 存在但连不上（mpv 没跑？）"
    fi
else
    warn "$IPC_PATH 不存在（mpv 未启动？）"
fi

# 4. 检查 MPRIS
echo
echo "═══ 4. MPRIS 检查 ═══"
if command -v playerctl >/dev/null; then
    PLAYERS=$(playerctl -l 2>&1)
    if echo "$PLAYERS" | grep -q "mpv"; then
        pass "mpv 在 MPRIS 注册"
        TITLE=$(playerctl -p mpv metadata --format '{{ artist }} - {{ title }}' 2>/dev/null)
        if [ -n "$TITLE" ] && [ "$TITLE" != " - " ]; then
            pass "MPRIS metadata: $TITLE"
        else
            warn "MPRIS metadata 空（mpv 可能在 idle）"
        fi
    else
        warn "mpv 不在 MPRIS 列表中（$PLAYERS）"
    fi
else
    fail "playerctl 未装"
fi

# 5. 检查 waybar config 语法
echo
echo "═══ 5. waybar config 语法检查 ═══"
TOP_CONFIG=~/.config/waybar/config-top
if [ -f "$TOP_CONFIG" ]; then
    if python3 -c "import json; json.load(open('$TOP_CONFIG'))" 2>/dev/null; then
        pass "config-top JSON 合法"
    else
        fail "config-top JSON 错误"
    fi
else
    warn "config-top 不存在: $TOP_CONFIG"
fi

# 6. 检查 sway config
echo
echo "═══ 6. sway config 检查 ═══"
if command -v sway >/dev/null; then
    SWAY_ERR=$(sway --validate 2>&1 || true)
    if echo "$SWAY_ERR" | grep -q "Unknown/invalid command\|Error on line"; then
        fail "sway config 有错:"
        echo "$SWAY_ERR" | head -5 | sed 's/^/      /'
    else
        pass "sway config 合法"
    fi
else
    warn "sway 未装"
fi

# 7. SWAYSOCK 检查
echo
echo "═══ 7. SWAYSOCK 检查（关键）═══"
SWAY_PID=$(for pid in /proc/[0-9]*; do
    [ -r "$pid/comm" ] || continue
    if [ "$(cat "$pid/comm" 2>/dev/null)" = "sway" ]; then
        echo "${pid##*/}"; break
    fi
done)
if [ -n "$SWAY_PID" ]; then
    REAL_SOCK="/run/user/$(id -u)/sway-ipc.$(id -u).${SWAY_PID}.sock"
    SHELL_SOCK="$SWAYSOCK"
    if [ -S "$REAL_SOCK" ]; then
        pass "实际 sway IPC: $REAL_SOCK"
        if [ "$SHELL_SOCK" = "$REAL_SOCK" ]; then
            pass "当前 shell SWAYSOCK 正确"
        elif [ -z "$SHELL_SOCK" ]; then
            warn "当前 shell 没设 SWAYSOCK"
        else
            fail "SWAYSOCK 不匹配: shell=$SHELL_SOCK 应为 $REAL_SOCK"
            echo "      修法: sway exec_always 用脚本从 /proc 找 sway PID"
        fi
    fi
else
    warn "找不到 sway 主进程（sway 没在跑？）"
fi

# 8. waybar 进程 SWAYSOCK
echo
echo "═══ 8. waybar 进程 SWAYSOCK ═══"
WB_PID=$(pgrep -f "waybar -c" | grep -v "bash -lic" | head -1)
if [ -n "$WB_PID" ]; then
    WB_SOCK=$(cat /proc/$WB_PID/environ 2>/dev/null | tr '\0' '\n' | grep ^SWAYSOCK= | cut -d= -f2)
    if [ -n "$WB_SOCK" ] && [ -S "$WB_SOCK" ]; then
        pass "waybar SWAYSOCK: $WB_SOCK"
    else
        fail "waybar SWAYSOCK 无效: $WB_SOCK"
    fi
else
    warn "waybar 没在跑"
fi

# 总结
echo
echo "═══ 总结 ═══"
echo "  ✓ $PASS 通过  ! $WARN 警告  ✗ $FAIL 失败"
exit $FAIL
