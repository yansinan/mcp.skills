#!/usr/bin/env python3
"""
Hermes Agent API Client — 跨机 agent 协作的可靠客户端库。

Token 节约核心策略：
1. session 复用：第一轮 ~25k tokens (system prompt),后续同 session 只追加增量
2. minimal follow-up：不用重复完整上下文，说 "继续上一步：做 X" 即可
3. 选对端点很重要（见各方法 docstring）

用法：
    client = HermesClient(BASE, KEY)
    
    # 模式 1：/v1/responses + conversation（推荐，session 自动合并）
    client.chat("记录：暗号是 PINEAPPLE", conversation="my-task")
    reply = client.chat("暗号是什么？", conversation="my-task")  # 同 session
    
    # 模式 2：/api/sessions/{id}/chat（显式 session 控制，同步返回）
    sid = client.create_session("my-task").id
    client.chat_in_session(sid, "执行步骤 1")
    client.chat_in_session(sid, "继续步骤 2")  # 同 session
    
    # 模式 3：/v1/runs（长任务，异步轮询）
    run_id = client.start_run("长任务", "my-task")
    result = client.wait_run(run_id)  # 轮询到 complete
"""

import json
import socket
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Optional


# ─── 响应类型 ───────────────────────────────────────────────────────

@dataclass
class RunResult:
    """/v1/runs 轮询终态"""
    run_id: str
    status: str            # completed / failed / cancelled
    output: Optional[str] = None
    session_id: Optional[str] = None
    usage: dict = field(default_factory=dict)


@dataclass
class SessionInfo:
    """/api/sessions 返回的 session 元数据"""
    id: str
    source: str = "api_server"
    title: Optional[str] = None
    message_count: int = 0
    tool_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    parent_session_id: Optional[str] = None


@dataclass
class ResponseResult:
    """/v1/responses 返回的响应片段"""
    response_id: str
    status: str
    text: str = ""
    usage: dict = field(default_factory=dict)
    output: list = field(default_factory=list)


# ─── HTTP 辅助 ──────────────────────────────────────────────────────

def _http(method: str, base: str, path: str,
          key: str, body: Any = None,
          timeout: int = 30) -> tuple[int, Any]:
    """单一 HTTP 请求，统一处理 JSON 编解码和错误"""
    url = base.rstrip("/") + "/" + path.lstrip("/")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        hint = e.read()[:2000].decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(hint)
        except json.JSONDecodeError:
            return e.code, {"error": hint}
    except Exception as e:
        return 0, {"error": f"{type(e).__name__}: {e}"}


def _poll(base: str, path: str, key: str,
           timeout_sec: int = 600, poll_interval: float = 2.0,
           terminal_statuses=frozenset({"completed", "failed", "cancelled", "error"})) -> dict:
    """轮询 GET 直到终态。自适应间隔：前 10 轮快，之后放慢。"""
    deadline = time.time() + timeout_sec
    round_n = 0
    while time.time() < deadline:
        round_n += 1
        _, resp = _http("GET", base, path, key, timeout=15)
        if isinstance(resp, dict):
            status = resp.get("status", "")
            if status in terminal_statuses:
                return resp
            # 自适应：前 10 轮 2s，之后 5s，超 30 轮 10s
            interval = poll_interval
            if round_n > 30:
                interval = 10.0
            elif round_n > 10:
                interval = 5.0
            time.sleep(interval)
    return {"status": "timeout", "error": f"poll timeout after {timeout_sec}s"}


# ─── 错误类型 ────────────────────────────────────────────────────────

class HermesAPIError(Exception):
    pass


# ─── 主客户端 ────────────────────────────────────────────────────────

class HermesClient:
    """Hermes Agent API Server 客户端

    参数：
        base: API server 地址，如 "http://100.66.66.249:8643"
        key: API_SERVER_KEY
        default_timeout: POST 超时（秒），默认 30
    """

    def __init__(self, base: str, key: str,
                 default_timeout: int = 30,
                 session_title_prefix: str = ""):
        self._base = base.rstrip("/")
        self._key = key
        self._timeout = default_timeout
        self._title_prefix = session_title_prefix or f"[from {socket.gethostname()}] "

    # ── 底层调用 ──────────────────────────────────────────────────

    def _post(self, path: str, body: dict, timeout: Optional[int] = None) -> tuple[int, Any]:
        return _http("POST", self._base, path, self._key, body,
                     timeout=timeout or self._timeout)

    def _patch(self, path: str, body: dict, timeout: Optional[int] = None) -> tuple[int, Any]:
        return _http("PATCH", self._base, path, self._key, body,
                     timeout=timeout or self._timeout)

    def _get(self, path: str, timeout: Optional[int] = None) -> tuple[int, Any]:
        return _http("GET", self._base, path, self._key, timeout=timeout or self._timeout)

    # ── 探活 ──────────────────────────────────────────────────────

    def ping(self) -> dict:
        """GET /v1/models — 端点是否存活"""
        code, body = self._get("/v1/models")
        if code == 200:
            return {"alive": True, "model": body.get("data", [{}])[0].get("id", "?")}
        return {"alive": False, "error": body}

    def capabilities(self) -> dict:
        """GET /v1/capabilities — 服务端功能探测"""
        _, body = self._get("/v1/capabilities")
        return body if isinstance(body, dict) else {}

    def health(self) -> dict:
        """GET /health（或 GET /v1/health）"""
        _, body = self._get("/health")
        return body if isinstance(body, dict) else {}

    # ── Session title 辅助 ──────────────────────────────────────

    def _set_session_title(self, session_id: str, title: str) -> bool:
        """PATCH /api/sessions/{id} 设 title（静默失败）"""
        if not session_id or not title:
            return False
        code, _ = self._patch(f"/api/sessions/{session_id}", {"title": title}, timeout=10)
        return code == 200

    # ── 模式 1：/v1/responses + conversation（推荐，session 自动合并）──

    def chat(self, input_text: str, *,
             conversation: Optional[str] = None,
             previous_response_id: Optional[str] = None,
             instructions: Optional[str] = None,
             store: bool = True,
             timeout: Optional[int] = None) -> ResponseResult:
        """POST /v1/responses

        推荐用于多轮对话。conversation 同名时自动接续并合并 session。

        Token 提示：
            - 第一轮 ~25k（system prompt），后续 n 轮约 input_text 长度
            - 用 conversation 不用手动管理 previous_response_id
            - instructions 只在第一轮设置，后续自动继承上下文
        """
        body: dict = {"input": input_text, "store": store}
        if conversation:
            body["conversation"] = self._title_prefix + conversation
        if previous_response_id:
            body["previous_response_id"] = previous_response_id
        if instructions:
            body["instructions"] = instructions

        code, resp = self._post("/v1/responses", body, timeout=timeout or 60)

        result = ResponseResult(
            response_id=resp.get("id", "") if isinstance(resp, dict) else "?",
            status=resp.get("status", "failed") if isinstance(resp, dict) else "http_error",
            usage=resp.get("usage", {}) if isinstance(resp, dict) else {},
            output=resp.get("output", []) if isinstance(resp, dict) else [],
        )

        if isinstance(resp, dict) and resp.get("output"):
            for item in resp["output"]:
                if item.get("type") == "message":
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            result.text += content["text"]

        # 补 session title：用 response_id 尝试（responses API 可能用它当 session_id）
        if result.response_id and conversation:
            self._set_session_title(result.response_id,
                                    self._title_prefix + conversation)

        return result

    # ── 模式 2：/api/sessions/{id}/chat（显式 session，同步返回）──

    def create_session(self, title: str = "") -> SessionInfo:
        """POST /api/sessions — 创建新 session（title 自动加前缀）"""
        final_title = self._title_prefix + title if title else ""
        body = {"title": final_title} if final_title else {}
        _, resp = self._post("/api/sessions", body)
        if isinstance(resp, dict) and "session" in resp:
            s = resp["session"]
            return SessionInfo(
                id=s.get("id", ""),
                source=s.get("source", "api_server"),
                title=s.get("title"),
                message_count=s.get("message_count", 0),
                tool_call_count=s.get("tool_call_count", 0),
                input_tokens=s.get("input_tokens", 0),
                output_tokens=s.get("output_tokens", 0),
                parent_session_id=s.get("parent_session_id"),
            )
        raise HermesAPIError(f"create_session failed: {resp}")

    def chat_in_session(self, session_id: str, input_text: str, *,
                        timeout: Optional[int] = None) -> str:
        """POST /api/sessions/{id}/chat — 在已有 session 中跑一轮

        同步返回，适合快速 follow-up。
        Token 提示：session 中已有系统 prompt + 前文，只追加增量。
        """
        code, resp = self._post(
            f"/api/sessions/{session_id}/chat",
            {"input": input_text},
            timeout=timeout or 60,
        )
        if code == 200 and isinstance(resp, dict):
            content = ""
            if "message" in resp:
                msg = resp["message"]
                if isinstance(msg, dict):
                    content = msg.get("content", "")
            elif "choices" in resp:
                for choice in resp.get("choices", []):
                    msg = choice.get("message", {})
                    content += msg.get("content", "")
            return content
        raise HermesAPIError(f"chat_in_session({session_id}) failed: {resp}")

    def get_session_messages(self, session_id: str, limit: int = 10) -> list[dict]:
        """GET /api/sessions/{id}/messages — 读 session 消息记录"""
        _, resp = self._get(f"/api/sessions/{session_id}/messages?limit={limit}")
        if isinstance(resp, dict):
            return resp.get("data", [])
        return []

    def list_sessions(self, limit: int = 10, source: str = "api_server") -> list[SessionInfo]:
        """GET /api/sessions — 列出最近 session"""
        _, resp = self._get(f"/api/sessions?limit={limit}&source={source}")
        sessions = []
        if isinstance(resp, dict):
            for s in resp.get("data", []):
                sessions.append(SessionInfo(
                    id=s.get("id", ""),
                    source=s.get("source", ""),
                    title=s.get("title"),
                    message_count=s.get("message_count", 0),
                    tool_call_count=s.get("tool_call_count", 0),
                    input_tokens=s.get("input_tokens", 0),
                    output_tokens=s.get("output_tokens", 0),
                    parent_session_id=s.get("parent_session_id"),
                ))
        return sessions

    # ── 模式 3：/v1/runs（异步长任务，轮询或 SSE）──

    def start_run(self, input_text: str, *,
                  conversation: Optional[str] = None,
                  previous_response_id: Optional[str] = None,
                  session_id: Optional[str] = None,
                  instructions: Optional[str] = None) -> str:
        """POST /v1/runs — 启动作业，返回 run_id

        Token 提示：
            - 用 previous_response_id 接续上下文，比重复发送完整任务省很多
            - /v1/runs 即使接续上下文，session 记录仍是独立的（不合并）
            - 如果需要 session 合并，用 chat() 或 chat_in_session()
        """
        body: dict = {"input": input_text}
        if conversation:
            body["conversation"] = self._title_prefix + conversation
        if previous_response_id:
            body["previous_response_id"] = previous_response_id
        if session_id:
            body["session_id"] = session_id
        if instructions:
            body["instructions"] = instructions

        code, resp = self._post("/v1/runs", body, timeout=15)
        if code == 202 and isinstance(resp, dict):
            return resp.get("run_id", "")
        raise HermesAPIError(f"start_run failed: {resp}")

    def get_run(self, run_id: str) -> RunResult:
        """GET /v1/runs/{run_id} — 查一次状态"""
        _, resp = self._get(f"/v1/runs/{run_id}")
        if isinstance(resp, dict):
            return RunResult(
                run_id=resp.get("run_id", run_id),
                status=resp.get("status", "unknown"),
                output=resp.get("output"),
                session_id=resp.get("session_id"),
                usage=resp.get("usage", {}),
            )
        return RunResult(run_id=run_id, status="error", output=f"API error: {resp}")

    def wait_run(self, run_id: str, timeout_sec: int = 600,
                 title: Optional[str] = None) -> RunResult:
        """轮询到终态。自适应间隔：2s → 5s → 10s。

        title: 可选，完成后补设 session title（如不传则跳过）。
        """
        resp = _poll(self._base, f"/v1/runs/{run_id}", self._key,
                     timeout_sec=timeout_sec)
        result = RunResult(
            run_id=resp.get("run_id", run_id),
            status=resp.get("status", "unknown"),
            output=resp.get("output"),
            session_id=resp.get("session_id") or run_id,  # fallback: run_id 本身就是 session_id
            usage=resp.get("usage", {}),
        )
        # 补 session title
        if result.status == "completed" and result.session_id and title:
            self._set_session_title(result.session_id, title)
        return result

    def stop_run(self, run_id: str) -> bool:
        """POST /v1/runs/{run_id}/stop — 中断运行"""
        code, _ = self._post(f"/v1/runs/{run_id}/stop", {})
        return code == 200

    # ── Token 节约辅助方法 ───────────────────────────────────────

    def follow_up(self, run_id: str, next_input: str, *,
                  conversation: Optional[str] = None,
                  instructions: Optional[str] = None) -> str:
        """快捷 follow-up：先确认前一轮完成，再起新 run 接续

        Token 提示：
            - 如果同一个 conversation，/v1/runs 不会自动合并 session
            - follow-up 用 previous_response_id（而非重复全量 prompt）
            - 或用 chat() 走 /v1/responses + conversation（自动合并）
        """
        result = self.wait_run(run_id)
        if result.status != "completed":
            raise HermesAPIError(
                f"Cannot follow up on run {run_id}: status={result.status}")

        if conversation:
            new_run_id = self.start_run(
                next_input,
                conversation=conversation,
                instructions=instructions,
            )
        elif result.session_id:
            new_run_id = self.start_run(
                next_input,
                session_id=result.session_id,
                instructions=instructions,
            )
        else:
            new_run_id = self.start_run(
                next_input,
                instructions=instructions,
            )

        title = self._title_prefix + conversation if conversation else None
        final = self.wait_run(new_run_id, title=title)
        return final.output or ""

    # ── 批量工具 ──────────────────────────────────────────────────

    def run_batch(self, inputs: list[str], *,
                  conversation: str,
                  poll_timeout: int = 600) -> list[str]:
        """同 conversation 下跑一系列任务（session 合并）

        Token 节约：
            - 只在第一轮付 system prompt 的 ~25k tokens
            - 后续轮次只有 input_text 的增量
            - 不要重复指令/setup，让 conversation 自己维护上下文
        """
        outputs = []
        run_id = ""
        first = True
        for inp in inputs:
            if first:
                run_id = self.start_run(inp, conversation=conversation)
                first = False
            else:
                try:
                    result = self.wait_run(run_id, timeout_sec=poll_timeout)
                    run_id = self.start_run(
                        inp,
                        conversation=conversation,
                    )
                except HermesAPIError:
                    run_id = self.start_run(inp, conversation=conversation)
            result = self.wait_run(run_id, timeout_sec=poll_timeout,
                                  title=self._title_prefix + conversation if conversation else None)
            outputs.append(result.output or "")
        return outputs

    # ── 跨机 skill 同步专用 ──────────────────────────────────────

    def tell(self, message: str, *, conversation: str = "hermes-skill-sync") -> str:
        """发送一条指令到远端 hermes。（用于 skill 同步场景）

        使用 /v1/responses + conversation，确保 session 合并。
        """
        result = self.chat(message, conversation=conversation)
        return result.text


# ─── 快速测试 ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    BASE = sys.argv[1] if len(sys.argv) > 1 else "http://100.66.66.249:8643"
    KEY = sys.argv[2] if len(sys.argv) > 2 else "Kino501502666666"

    client = HermesClient(BASE, KEY, session_title_prefix="[test] ")

    print("=" * 50)
    print("Ping:", client.ping())
    print()

    print("== Session 复用演示: /v1/responses + conversation ==")
    r1 = client.chat("记住暗号: PINEAPPLE。确认即可。", conversation="demo-session")
    print(f"  Turn 1: {r1.text[:80]}")
    r2 = client.chat("暗号是什么？", conversation="demo-session")
    print(f"  Turn 2: {r2.text[:80]}")
    print(f"  两个 turn 的 session 合并了吗？→ 查看 /api/sessions 确认\n")

    print("== 显式 Session 控制: /api/sessions/{id}/chat ==")
    try:
        sess = client.create_session("demo-chat")
        print(f"  Created session: {sess.id}")
        reply1 = client.chat_in_session(sess.id, "说 Hello from session")
        print(f"  Turn 1: {reply1[:80]}")
        reply2 = client.chat_in_session(sess.id, "再说一次 Hello")
        print(f"  Turn 2: {reply2[:80]}")
    except HermesAPIError as e:
        print(f"  (Sessions API not available: {e})")

    print("== 长任务异步: /v1/runs ==")
    rid = client.start_run("'设备名是什么？'", conversation="demo-run")
    print(f"  Run ID: {rid}")
    final = client.wait_run(rid, timeout_sec=60,
                            title=client._title_prefix + "demo-run")
    print(f"  Status: {final.status}")
    if final.output:
        print(f"  Output: {final.output[:200]}")
    print(f"  Usage: input_tok={final.usage.get('input_tokens')} "
          f"output_tok={final.usage.get('output_tokens')}")
