#!/usr/bin/env bash
# validate-swayidle-config.sh - 检查 swayidle config 是否踩 parse_command argv0 陷阱
# 用法: bash validate-swayidle-config.sh [config_path]
#       默认检查 ~/.config/swayidle/config

set -euo pipefail

CONFIG="${1:-$HOME/.config/swayidle/config}"

if [[ ! -f "$CONFIG" ]]; then
    echo "❌ 配置文件不存在: $CONFIG"
    exit 1
fi

echo "=== 检查 $CONFIG ==="
echo

ERRORS=0
LINE_NUM=0
HAS_RESUME=false
RESUME_LINE=0

while IFS= read -r line; do
    LINE_NUM=$((LINE_NUM + 1))
    # 跳过空行和注释
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

    # 拆出 timeout 命令
    if [[ "$line" =~ ^timeout[[:space:]]+([0-9]+)[[:space:]]+(.*)$ ]]; then
        seconds="${BASH_REMATCH[1]}"
        rest="${BASH_REMATCH[2]}"
        # rest 可能是 "cmd args... resume cmd2 args2..."
        # 取第一个 token（argv[2]）
        first_token=$(echo "$rest" | awk '{print $1}')

        # 检查是否被引号包裹
        if [[ "$first_token" =~ ^\'.*\'$ ]] || [[ "$first_token" =~ ^\".*\"$ ]]; then
            echo "✅ L$LINE_NUM: timeout $seconds ${rest:0:50}..."
            continue
        fi

        # 检查 token 之后是否有更多 token（说明带参数）
        token_count=$(echo "$rest" | wc -w)
        # 如果出现 "resume" 关键字，token 数会 > 1（命令 + resume + ...）
        if [[ "$rest" =~ [[:space:]]resume[[:space:]] ]]; then
            # parse_command 只看 argv[2] = 第一个 token。resume 之后的 argv[4] 同理
            # 所以 idle_cmd 和 resume_cmd 都需要检查
            idle_cmd=$(echo "$rest" | awk '{print $1}')
            resume_cmd=$(echo "$rest" | awk '{for(i=1;i<=NF;i++) if($i=="resume") {print $(i+1); exit}}')
            echo "❌ L$LINE_NUM: timeout $seconds"
            echo "   idle_cmd   = $idle_cmd"
            echo "   resume_cmd = $resume_cmd"
            echo "   问题: 这两个 token 后面的参数都会被丢弃（parse_command 只取 argv[0]）"
            echo "   修复:"
            echo "     timeout $seconds '$idle_cmd --你的参数' resume '$resume_cmd --你的参数'"
            ERRORS=$((ERRORS + 1))
        else
            # 没有 resume，可能是 timeout N cmd args
            if [[ $token_count -gt 1 ]]; then
                echo "❌ L$LINE_NUM: timeout $seconds $rest"
                echo "   问题: argv[2] = '$first_token'，后续参数 $(echo "$rest" | awk '{for(i=2;i<=NF;i++) printf "%s ", $i}')丢失"
                echo "   修复: timeout $seconds '$rest'"
                ERRORS=$((ERRORS + 1))
            else
                echo "✅ L$LINE_NUM: timeout $seconds $first_token (单 token 命令，无需引号)"
            fi
        fi
    fi
done < "$CONFIG"

echo
if [[ $ERRORS -gt 0 ]]; then
    echo "=== 发现 $ERRORS 处问题 ==="
    echo "详见 references/swayidle-parse-command-argv0-bug.md"
    exit 1
else
    echo "=== 全部 OK ==="
    exit 0
fi