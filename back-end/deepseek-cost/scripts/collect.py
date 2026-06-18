#!/usr/bin/env python3
"""DeepSeek 成本数据采集器

两种运行模式:
  1. 默认 (cron agent):     输出完整 JSON 分析报告 → cron 分析用
  2. --waybar:              输出 Waybar JSON → 状态栏显示

Waybar 用法:
  python3 collect.py --waybar
  → JSON: {"text": " ¥12.34", "alt": "ok", "class": "ok",
           "tooltip": "<b>DeepSeek 余额</b>\\n..."}

  在 config-top 的 modules-right 中添加:
  "custom/deepseek-cost": {
    "exec": "python3 /path/to/collect.py --waybar",
    "return-type": "json",
    "interval": 300,
    "tooltip": true
  }

充值感知: 检测余额跳涨 ≥ ¥8 → 标记 recharge 事件 → 充值后区间隔离分析。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.request
import ssl
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DATA_DIR = SKILL_DIR / "data"
HISTORY_FILE = DATA_DIR / "balance_history.json"

TZ = timezone(timedelta(hours=8))  # Asia/Shanghai
RECHARGE_THRESHOLD = 8.0           # ≥ ¥8 视为充值（每笔 ¥10）
WARN_BALANCE = 10.0                # 黄色预警
CRIT_BALANCE = 5.0                 # 红色警戒
HISTORY_MAX = 90                   # 保留条目

# Nerd Font 图标
ICON = "\uf09d"  #   credit-card

# ── emit() ────────────────────────────────────────────

def emit_waybar(text: str, alt: str, tooltip: str = "") -> None:
    """统一 Waybar JSON 输出"""
    print(json.dumps({
        "text": text,
        "alt": alt,
        "class": alt,
        "tooltip": tooltip,
    }, ensure_ascii=False))
    sys.exit(0)


def fail_waybar(reason: str) -> None:
    """Waybar 模式下优雅降级"""
    emit_waybar(f"{ICON} ✗", "error", f"<span color='#e74c3c'>采集失败</span>\n{reason}")


# ── API 采集 ──────────────────────────────────────────

def _load_api_key() -> str:
    """从环境变量或 ~/.config/environment.d/99-deepseek.conf 获取 key。"""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    # Fallback: waybar 走 sway exec_always，不继承 systemd env，直接读文件
    env_file = Path.home() / ".config" / "environment.d" / "99-deepseek.conf"
    if env_file.exists():
        try:
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    k = line.split("=", 1)[1].strip().strip("\"'")
                    if k:
                        return k
        except OSError:
            pass
    return ""


def get_balance() -> dict:
    """查询 DeepSeek 余额 API。"""
    key = _load_api_key()
    if not key:
        return {"error": "DEEPSEEK_API_KEY not set in environment or ~/.config/environment.d/*.conf"}
    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/user/balance",
            headers={"Accept": "application/json", "Authorization": f"Bearer {key}"},
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def get_insights(days: int = 3) -> dict:
    """执行 hermes insights 并解析 token 统计。"""
    try:
        result = subprocess.run(
            ["hermes", "insights", "--days", str(days)],
            capture_output=True, text=True, timeout=30,
        )
        return parse_insights(result.stdout)
    except Exception as e:
        return {"error": str(e)}


def _strip_emoji(text: str) -> str:
    """移除 emoji 符号，保留表格边框字符。"""
    result = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat not in ("So", "Cn"):
            result.append(ch)
        elif ch in ("─", "╔", "╗", "╚", "╝", "║"):
            result.append(ch)
    return "".join(result)


def _extract_int(text: str) -> int:
    """提取文本中第一个整数。"""
    for token in text.replace(",", "").split():
        try:
            return int(token)
        except ValueError:
            continue
    return 0


# ── Insights 解析（增强版）──────────────────────────────

INSIGHTS_PATTERNS = {
    "total_input_tokens": re.compile(r"Input\s*tokens?\s*:?\s*([\d,]+)", re.I),
    "total_output_tokens": re.compile(r"Output\s*tokens?\s*:?\s*([\d,]+)", re.I),
    "total_tokens": re.compile(r"Total\s*tokens?\s*:?\s*([\d,]+)", re.I),
    "sessions": re.compile(r"Sessions?\s*:?\s*([\d,]+)", re.I),
}

MODEL_LINE = re.compile(
    r"^\s*(\S[^A-Z]*?)\s+([\d,]+)\s+([\d,]+)\s*$"
)
PLATFORM_LINE = re.compile(
    r"^\s*([A-Za-z]\S*)\s+([\d,]+)\s*$"
)


def parse_insights(text: str) -> dict:
    """用正则解析 hermes insights 输出，比原版逐行 if-else 更健壮。"""
    data = {
        "total_input_tokens": 0, "total_output_tokens": 0,
        "total_tokens": 0, "sessions": 0,
        "models": {}, "platforms": {},
        "raw_error": None,
    }

    # 先走正则提取汇总字段
    for key, pat in INSIGHTS_PATTERNS.items():
        m = pat.search(text)
        if m:
            data[key] = _extract_int(m.group(1))

    # 定位 sections
    lines = text.split("\n")
    clean = [_strip_emoji(l) for l in lines]
    model_start = platform_start = None
    for i, c in enumerate(clean):
        if "Models Used" in c:
            model_start = i + 1
        if "Platforms" in c:
            platform_start = i + 1

    # Models 表（跳过表头行）
    if model_start:
        for c in lines[model_start:]:
            cs = c.strip()
            if not cs or cs.startswith("──") or cs.startswith("══"):
                continue
            if any(kw in cs for kw in ("Platforms", "Top Tools", "Top Skills")):
                break
            m = MODEL_LINE.match(cs)
            if m:
                name = m.group(1).strip()
                try:
                    s = int(m.group(2).replace(",", ""))
                    t = int(m.group(3).replace(",", ""))
                    data["models"][name] = {"sessions": s, "tokens": t}
                except ValueError:
                    pass

    # Platforms 表
    if platform_start:
        for c in lines[platform_start:]:
            cs = c.strip()
            if not cs or cs.startswith("──") or cs.startswith("══"):
                continue
            if any(kw in cs for kw in ("Top Tools", "Top Skills")):
                break
            m = PLATFORM_LINE.match(cs)
            if m:
                try:
                    data["platforms"][m.group(1)] = _extract_int(m.group(2))
                except ValueError:
                    pass

    return data


# ── 历史持久化 ────────────────────────────────────────

def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_history(history: list) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # 去重：同一分钟内同余额不重复写
    if len(history) >= 2:
        a, b = history[-2], history[-1]
        try:
            same_bal = a.get("total_balance") == b.get("total_balance")
            same_min = a.get("timestamp", "")[:16] == b.get("timestamp", "")[:16]
            if same_bal and same_min:
                history.pop()
        except (IndexError, KeyError):
            pass
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2))


# ── 充值检测 ──────────────────────────────────────────

def detect_recharges(history: list) -> None:
    """标记充值事件（余额跳涨 ≥ ¥8）。"""
    for i, entry in enumerate(history):
        if i == 0:
            entry.pop("recharge", None)
            continue
        prev = float(history[i - 1].get("total_balance", 0))
        curr = float(entry.get("total_balance", 0))
        gain = curr - prev
        if gain >= RECHARGE_THRESHOLD:
            entry["recharge"] = True
            entry["recharge_amount"] = round(gain, 2)
        else:
            entry.pop("recharge", None)


def find_last_recharge_idx(history: list) -> int:
    """返回最后一次充值索引，-1 表示从未充值。"""
    for i in range(len(history) - 1, -1, -1):
        if history[i].get("recharge"):
            return i
    return -1


# ── 余额状态判定 ─────────────────────────────────────

def balance_class(total: float) -> str:
    """返回 CSS class: critical / warning / ok"""
    if total < CRIT_BALANCE:
        return "critical"
    if total < WARN_BALANCE:
        return "warning"
    return "ok"


def balance_icon(total: float) -> str:
    """根据余额返回对应状态图标。"""
    if total < CRIT_BALANCE:
        return "\u26a0\ufe0f"  # ⚠️
    return ICON


# ── 消费分析（充值感知版）─────────────────────────────────

def analyze(history: list, current_balance: dict) -> dict:
    """返回 {alerts, insights, recharge_events}。"""
    alerts: list[str] = []
    insights: list[str] = []
    recharge_events: list[str] = []

    total = float(current_balance.get("total_balance", 0))
    is_avail = current_balance.get("is_available", True)

    # ── 余额告警 ──
    if total < CRIT_BALANCE:
        alerts.append(f"余额仅 ¥{total:.2f}，低于 ¥{CRIT_BALANCE:.0f} 警戒线！请尽快充值。")
    elif total < WARN_BALANCE:
        alerts.append(f"余额 ¥{total:.2f}，接近警戒线（< ¥{WARN_BALANCE:.0f}），建议关注。")
    if not is_avail:
        alerts.append("DeepSeek 标记为不可用（is_available=false）！")

    # ── 充值检测 ──
    detect_recharges(history)
    last_recharge_idx = find_last_recharge_idx(history)

    for entry in history:
        if entry.get("recharge") and "recharge_amount" in entry:
            ts = entry.get("timestamp", "?")[:16]
            recharge_events.append(f"充值 +¥{entry['recharge_amount']:.2f} @ {ts}")

    # ── 消费速率 ──
    if len(history) < 2:
        if recharge_events:
            insights.append("检测到充值事件，消费基线已重置。历史数据不足，暂无法计算速率。")
        else:
            insights.append("历史数据不足，需积累至少 2 条采样才可计算速率")
        return {"alerts": alerts, "insights": insights, "recharge_events": recharge_events}

    # 充值后有效区间
    start_idx = max(last_recharge_idx, 0)
    effective_history = history[start_idx:]

    if len(effective_history) < 2:
        insights.append("最近一次充值后采样不足，需积累至少 2 条充值后数据")
        return {"alerts": alerts, "insights": insights, "recharge_events": recharge_events}

    prev = effective_history[-2]
    prev_balance = float(prev.get("total_balance", 0))
    drop = prev_balance - total

    # 时间差
    try:
        now_ts = datetime.fromisoformat(current_balance.get("timestamp", ""))
        prev_ts = datetime.fromisoformat(prev.get("timestamp", ""))
        hours_diff = max((now_ts - prev_ts).total_seconds() / 3600, 0.01)
    except (ValueError, TypeError):
        hours_diff = 24

    # 跳过充值采样点的速率计算（余额上涨）
    if drop < -0.01:
        if hours_diff >= 1.0:
            insights.append(f"余额较上次增长 ¥{-drop:.4f}，可能为 API 精度波动（未达充值阈值），速率暂不可靠")
        return {"alerts": alerts, "insights": insights, "recharge_events": recharge_events}

    # ── 速率 ──
    if hours_diff < 1.0:
        insights.append(f"间隔 {hours_diff:.1f}h（< 1h，速率不可靠），消耗 ¥{drop:.4f}（仅供参考）")
        if len(alerts) == 0:
            insights.append("需积累至少 1h 间隔数据才可做准确预测")
        return {"alerts": alerts, "insights": insights, "recharge_events": recharge_events}

    hourly = drop / hours_diff
    insights.append(f"间隔 {hours_diff:.1f}h，消耗 ¥{drop:.4f} (≈¥{hourly:.4f}/h)")

    # ── 翻倍异常 ──
    if len(effective_history) >= 3:
        prev2 = effective_history[-3]
        prev2_balance = float(prev2.get("total_balance", 0))
        prev_drop = prev2_balance - prev_balance
        if prev_drop > 0.001 and drop > prev_drop * 2:
            ratio = drop / prev_drop
            alerts.append(
                f"消费异常飙升！近 {hours_diff:.0f}h 消耗 ¥{drop:.4f}，"
                f"是前段 ¥{prev_drop:.4f} 的 {ratio:.1f}x 倍"
            )

    # ── 耗尽预测 ──
    if hourly > 0.001 and total > 0:
        days_left = total / hourly / 24
        insights.append(f"按当前速率，预计余额可支撑 {days_left:.1f} 天")
        if days_left < 3:
            alerts.append(f"预计 {days_left:.1f} 天后余额耗尽！")
        elif days_left < 7:
            insights.append("一周内可能需要充值")

    return {"alerts": alerts, "insights": insights, "recharge_events": recharge_events}


# ── 输出格式 ──────────────────────────────────────────

def format_waybar(current_balance: dict, history: list,
                  analysis: dict) -> None:
    """输出 Waybar JSON。"""
    total = float(current_balance.get("total_balance", 0))
    cls = balance_class(total)
    icon = balance_icon(total)

    # -- text: 简短的余额显示 --
    text = f"{icon} ¥{total:.2f}"

    # -- alt: 状态简码 --
    alt = cls

    # -- tooltip: 多行详情（Pango markup，动态数据用 html.escape 转义） --
    import html
    granted = current_balance.get("granted_balance", "0")
    topped = current_balance.get("topped_up_balance", "0")
    esc = html.escape
    lines = ["<b>DeepSeek 余额</b>"]
    lines.append(f"  总余额: <b>¥{total:.2f}</b>")
    lines.append(f"  可用: {'✓' if current_balance.get('is_available', False) else '✗'}")
    lines.append(f"  <span color='#888'>赠送: ¥{esc(str(granted))} | 充值: ¥{esc(str(topped))}</span>")

    if analysis["insights"]:
        lines.append("")
        lines.append("<b>消费分析</b>")
        for ins in analysis["insights"][:5]:
            lines.append(f"  {esc(ins)}")

    if analysis["recharge_events"]:
        lines.append("")
        lines.append("<b>充值记录</b>")
        for ev in analysis["recharge_events"][-3:]:
            lines.append(f"  {esc(ev)}")

    if analysis["alerts"]:
        lines.append("")
        lines.append("<span color='#e74c3c'><b>告警</b></span>")
        for a in analysis["alerts"]:
            lines.append(f"  <span color='#e74c3c'>⚠ {esc(a)}</span>")

    ts = current_balance.get("timestamp", "")[:19]
    lines.append("")
    lines.append(f"<span size='small' color='#666'>{esc(ts)}</span>")

    tooltip = "\n".join(lines)
    emit_waybar(text, alt, tooltip)


def format_cron(balance: dict, insights_data: dict | None,
                history: list, analysis: dict,
                mode: str, now: str) -> dict:
    """输出完整 JSON（cron/direct 模式）。"""
    return {
        "collected_at": now,
        "mode": mode,
        "balance": balance,
        "alerts": analysis["alerts"],
        "recharge_events": analysis["recharge_events"],
        "analysis": analysis["insights"],
        "history_count": len(history),
        "insights_3day": insights_data,
    }


# ── 入口 ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="DeepSeek 成本采集器")
    parser.add_argument("--balance-only", action="store_true",
                        help="仅采集余额，跳过 hermes insights（快速模式）")
    parser.add_argument("--days", type=int, default=3,
                        help="insights 统计天数（默认 3）")
    parser.add_argument("--waybar", action="store_true",
                        help="输出 Waybar JSON（状态栏显示）")
    args = parser.parse_args()

    now = datetime.now(TZ).isoformat()

    # 采集余额
    balance = get_balance()

    if "error" in balance:
        if args.waybar:
            fail_waybar(balance["error"])
        else:
            print(json.dumps({"error": balance["error"], "collected_at": now},
                             ensure_ascii=False, indent=2))
            sys.exit(1)

    # 采集 insights（仅全量模式）
    insights_data = None
    if not args.balance_only:
        insights_data = get_insights(args.days)

    # 构造余额记录
    info = balance.get("balance_infos", [{}])[0] if "balance_infos" in balance else {}
    current_balance = {
        "timestamp": now,
        "total_balance": info.get("total_balance", "0"),
        "granted_balance": info.get("granted_balance", "0"),
        "topped_up_balance": info.get("topped_up_balance", "0"),
        "is_available": balance.get("is_available", False),
    }

    # 持久化
    history = load_history()
    history.append(current_balance)
    history = history[-HISTORY_MAX:]
    save_history(history)

    # 分析
    analysis = analyze(history, current_balance)

    # 输出
    if args.waybar:
        format_waybar(current_balance, history, analysis)
    else:
        output = format_cron(
            current_balance, insights_data, history,
            analysis,
            "balance_only" if args.balance_only else "full",
            now,
        )
        print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
