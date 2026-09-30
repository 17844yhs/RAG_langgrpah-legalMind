"""API 集成测试：SSE 流式契约 — FakeWorkflow 替换图层，验证 HTTP 侧行为

覆盖：session_id 首发事件、stage 透传、token 累积、sources/usage 收尾、[DONE]；
灰盒一小块：流结束后翻数据库验证消息与 token usage JSONB 落库。
"""
from types import SimpleNamespace

from langchain_core.messages import AIMessageChunk

import app.api.chat as chat_mod
from app.llm.usage_tracker import usage_var
from app.models.chat import ChatMessageRecord
from tests.api.conftest import parse_sse


class FakeGraph:
    """aget_state 的假图：_finalize_stream/_check_pending/_check_interrupt 从这里读 state

    next/interrupts 可在测试中途中改（fake._graph._next = (...)）模拟崩溃后 pending
    """
    def __init__(self, values, next=(), interrupts=None):
        self._values = values
        self._next = next
        self._interrupts = interrupts or []

    async def aget_state(self, config):
        task = SimpleNamespace(interrupts=self._interrupts)
        return SimpleNamespace(values=self._values, next=self._next, tasks=[task])


class FakeWorkflow:
    """usage：模拟 LLM 回调在请求上下文内累加 token（TraceIdMiddleware 每请求
    会建新账本，所以累加必须发生在流式过程中而非测试里预置——与生产行为一致）"""
    def __init__(self, events=None, final_values=None, usage=None):
        self._events = events or []
        self._graph = FakeGraph(final_values or {})
        self._usage = usage

    async def astream(self, query, thread_id, **kw):
        if self._usage:
            ledger = usage_var.get()
            if ledger:
                ledger.add(*self._usage)
        for e in self._events:
            yield e

    async def astream_continue(self, thread_id, **kw):
        """崩溃恢复续跑：无新输入，事件流与 astream 同构（测试共用 _events）"""
        if self._usage:
            ledger = usage_var.get()
            if ledger:
                ledger.add(*self._usage)
        for e in self._events:
            yield e

    def get_graph(self):
        return self._graph


def _fake_events():
    """复刻 workflow 层归一化后的统一事件流（stage / token 双类型）"""
    return [
        {"type": "stage", "stage": {"stage": "retrieval", "status": "done",
                                    "text": "找到 1 条相关案例"}},
        {"type": "token", "chunk": AIMessageChunk(content="你好，"),
         "metadata": {"langgraph_node": "qa_generation"}},
        {"type": "token", "chunk": AIMessageChunk(content="根据劳动合同法"),
         "metadata": {"langgraph_node": "qa_generation"}},
        # 干扰项：非 qa_generation 节点的 token 不应进入正文
        {"type": "token", "chunk": AIMessageChunk(content="[内部]"),
         "metadata": {"langgraph_node": "intent_recognition"}},
    ]


def _patch(monkeypatch, events=None, final_values=None, usage=None):
    fake = FakeWorkflow(events if events is not None else _fake_events(),
                        final_values, usage)
    monkeypatch.setattr(chat_mod, "workflow", fake)
    return fake


async def test_stream_sse_contract(client, auth_headers, monkeypatch):
    """完整 SSE 事件序列：session_id → stage → content×N → sources → usage → [DONE]"""
    _patch(monkeypatch, final_values={"sources": ["(2023)京01民终1234号"],
                                      "answer_meta": None},
           usage=(100, 50))

    resp = await client.post("/api/v1/chat/stream", headers=auth_headers,
                             json={"message": "工伤赔偿怎么算"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(resp.text)
    # 首事件是 session_id（前端新会话需要它来 resume）
    assert "session_id" in events[0]
    # stage 事件原样透传（前端进度条数据源）
    assert events[1]["stage"]["stage"] == "retrieval"
    # 只有 qa_generation 节点的 token 进入正文（干扰项被过滤）
    contents = [e["content"] for e in events if "content" in e]
    assert contents == ["你好，", "根据劳动合同法"]
    # 收尾：sources → usage → [DONE]
    assert events[-1] == {"done": True}
    assert events[-2]["usage"] == {"input_tokens": 100, "output_tokens": 50,
                                   "total_tokens": 150, "calls": 1}
    assert events[-3]["sources"] == ["(2023)京01民终1234号"]


async def test_stream_persists_messages_with_usage(client, auth_headers, monkeypatch):
    """灰盒收尾：流结束后 user/assistant 两条记录落库，usage 以 JSONB 持久化"""
    _patch(monkeypatch, final_values={"sources": ["来源1"], "answer_meta": None},
           usage=(70, 30))

    resp = await client.post("/api/v1/chat/stream", headers=auth_headers,
                             json={"message": "试用期被辞退怎么办"})

    events = parse_sse(resp.text)
    session_id = events[0]["session_id"]

    records = await ChatMessageRecord.filter(chat_session__session_id=session_id) \
                                     .order_by("id")
    assert [r.role for r in records] == ["user", "assistant"]
    assert records[0].content == "试用期被辞退怎么办"
    assert records[1].content == "你好，根据劳动合同法"    # 流式累积的完整正文
    assert records[1].usage == {"input_tokens": 70, "output_tokens": 30,
                                "total_tokens": 100, "calls": 1}


async def test_stream_appexception_becomes_sse_error_event(client, auth_headers, monkeypatch):
    """业务异常不走 HTTP 状态码，而是在流内以 error 事件传递（SSE 200 语义）"""
    from app.exceptions import AppException, ErrorCode

    class BoomWorkflow(FakeWorkflow):
        async def astream(self, query, thread_id, **kw):
            raise AppException(ErrorCode.RAG_RETRIEVAL_FAILED)
            yield  # pragma: no cover — 使其成为 async generator

    monkeypatch.setattr(chat_mod, "workflow", BoomWorkflow())

    resp = await client.post("/api/v1/chat/stream", headers=auth_headers,
                             json={"message": "触发异常"})
    assert resp.status_code == 200    # SSE 已开始，HTTP 层不回错

    events = parse_sse(resp.text)
    assert events[-1] == {"done": True}
    err = events[-2]["error"]
    assert err["code"] == "RAG_001"
    assert err["detail"] == "检索服务暂时不可用"
    assert err["traceId"]


async def test_stream_unexpected_error_masks_detail(client, auth_headers, monkeypatch):
    """未知异常：对外只给 SYS_001 + traceId，不泄露内部信息"""
    class CrashWorkflow(FakeWorkflow):
        async def astream(self, query, thread_id, **kw):
            raise RuntimeError("数据库连接串 postgresql://user:secret@host/db 泄露风险")
            yield  # pragma: no cover

    monkeypatch.setattr(chat_mod, "workflow", CrashWorkflow())

    resp = await client.post("/api/v1/chat/stream", headers=auth_headers,
                             json={"message": "触发崩溃"})
    events = parse_sse(resp.text)
    err = events[-2]["error"]
    assert err["code"] == "SYS_001"
    assert "secret" not in resp.text          # 敏感信息不出内网日志


# ── 崩溃/断线恢复（durable execution）：pending 探测 + /continue 续跑 ──

async def _create_session(client, auth_headers, monkeypatch, final_values=None, usage=None):
    """先走一次 stream 建会话（归属校验需要库里有这条 session），返回 (fake, session_id)。

    建会话用空事件流（无 token → full_text 空 → 不落库），这样 continue 的
    落库断言才能干净地数出且仅数出续跑轮次的 user/assistant 两条；
    usage 也延后到 continue 阶段注入，避免建会话轮次先把 token 记掉。
    """
    fake = _patch(monkeypatch, events=[], final_values=final_values)
    resp = await client.post("/api/v1/chat/stream", headers=auth_headers,
                             json={"message": "工伤赔偿怎么计算"})
    sid = parse_sse(resp.text)[0]["session_id"]
    fake._events = _fake_events()
    fake._usage = usage
    return fake, sid


async def test_pending_endpoint_reports_crash_recovery(client, auth_headers, monkeypatch):
    """探测端点：next 非空且无 interrupt → 故障中断（前端显示「继续生成」按钮）"""
    fake, sid = await _create_session(client, auth_headers, monkeypatch)
    fake._graph._next = ("qa_generation",)    # 模拟崩溃后图停在节点边界

    resp = await client.get(f"/api/v1/chat/sessions/{sid}/pending", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == {"pending": True, "interrupted": False}


async def test_pending_endpoint_reports_hitl_interrupt(client, auth_headers, monkeypatch):
    """探测端点：next 非空 + 有 interrupt → HITL 场景（问答卡片接管，不显示继续按钮）"""
    fake, sid = await _create_session(client, auth_headers, monkeypatch)
    fake._graph._next = ("check_intent",)
    fake._graph._interrupts = [SimpleNamespace(value={"type": "confirm_intent"})]

    resp = await client.get(f"/api/v1/chat/sessions/{sid}/pending", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == {"pending": True, "interrupted": True}


async def test_continue_streams_and_persists(client, auth_headers, monkeypatch):
    """/continue：input=None 续跑产出 SSE 流，收尾以 checkpoint state 里的 query 落库"""
    fake, sid = await _create_session(
        client, auth_headers, monkeypatch,
        final_values={"query": "工伤赔偿怎么计算", "sources": ["来源1"], "answer_meta": None},
        usage=(60, 40),
    )
    fake._graph._next = ("qa_generation",)    # 崩溃 pending

    resp = await client.post("/api/v1/chat/continue", headers=auth_headers,
                             json={"session_id": sid})

    assert resp.status_code == 200
    events = parse_sse(resp.text)
    assert [e["content"] for e in events if "content" in e] == ["你好，", "根据劳动合同法"]

    # 落库：query 取自 checkpoint state（本请求无新输入），两条消息补齐
    records = await ChatMessageRecord.filter(chat_session__session_id=sid).order_by("id")
    assert [r.role for r in records] == ["user", "assistant"]
    assert records[0].content == "工伤赔偿怎么计算"
    assert records[1].content == "你好，根据劳动合同法"
    assert records[1].usage == {"input_tokens": 60, "output_tokens": 40,
                                "total_tokens": 100, "calls": 1}


async def test_continue_409_when_nothing_pending(client, auth_headers, monkeypatch):
    """/continue：图已结束（next 空）→ 409 CHAT_002，前端据此隐藏按钮"""
    _patch(monkeypatch)                        # 默认 next=()
    resp = await client.post("/api/v1/chat/stream", headers=auth_headers,
                             json={"message": "工伤赔偿怎么计算"})
    sid = parse_sse(resp.text)[0]["session_id"]

    resp = await client.post("/api/v1/chat/continue", headers=auth_headers,
                             json={"session_id": sid})

    assert resp.status_code == 409
    assert resp.json()["code"] == "CHAT_002"
