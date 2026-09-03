"""集成测试（白盒）：LangGraph 主图逻辑 — 用 Fake 组件替换所有 LLM 依赖

┌─────────────────────────── 测试定位───────────────────────────┐
│ 级别（测多大） 集成测试：真实的图引擎+路由+条件边+状态合并拼起来跑          │
│               → 不是单函数（那是 unit/），也不是全系统（那是 E2E）          │
│ 方法（什么视角）白盒：断言内部状态（reflection_round/反馈注入/messages）     │
│               → 必须打开盒子才写得出这些断言，黑盒做不到                    │
│ 手段（怎么控） LLM/检索/checkpoint 全换 mock 和假实现                      │
│               → 控制不确定性：LLM 不确定，mock 它；                        │
│                 图的路由和状态流转确定，测它                                │
└──────────────────────────────────────────────────────────────────────────┘

策略（面试可讲）：LLM 输出不确定，所以 mock 边界、只测确定的部分——
- get_checkpointer → MemorySaver（不依赖 PostgreSQL）
- retrieval_subgraph / info_gathering / 各 Agent 方法 → stub
验证的是图的确定性逻辑：路由、质量门控三路径、HITL interrupt/resume、
草稿不入对话历史、反馈注入。
"""
import json
import uuid

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

import app.agents.workflow as wf
from tests.conftest import FAKE_CASE, make_intent_result, make_verdict


# ── 夹具与 stub 工厂 ──

@pytest.fixture
def workflow():
    """主图单例。测试结束强制重建，防止 stub 节点残留到其他测试。"""
    instance = wf.workflow
    instance._graph = None
    yield instance
    instance._graph = None


def make_stream_stub(answers: list[str], calls: list):
    async def stream_answer(cases, messages, summary=None, reflection_feedback=None):
        calls.append({"reflection_feedback": reflection_feedback})
        text = answers[min(len(calls) - 1, len(answers) - 1)]
        yield AIMessageChunk(content=text)
    return stream_answer


def make_reflect_stub(verdicts: list, calls: list):
    async def reflect_answer(response, cases, query):
        calls.append(response)
        return verdicts.pop(0)
    return reflect_answer


def patch_common(monkeypatch, workflow, *, intent="qa", confidence=0.95):
    """公共桩：checkpointer + 检索子图 + 信息收集 + 意图识别"""
    monkeypatch.setattr(wf, "get_checkpointer", lambda: MemorySaver())

    async def fake_retrieval(state):
        return {"retrieved_cases": [dict(FAKE_CASE)]}
    monkeypatch.setattr(wf, "retrieval_subgraph", fake_retrieval)

    async def info_ok(state):
        return {"info_sufficient": True}
    monkeypatch.setattr(wf, "info_gathering", info_ok)

    async def recognize(query):
        return make_intent_result(intent, confidence)
    monkeypatch.setattr(workflow.intent_agent, "recognize", recognize)

    async def extract_meta(text):
        return None
    monkeypatch.setattr(workflow.qa_agent, "extract_meta", extract_meta)

    monkeypatch.setattr(workflow.qa_agent, "_extract_sources", lambda cases: ["来源1"])


def build(workflow):
    return workflow.get_graph()


def _config():
    return {"configurable": {"thread_id": f"t-{uuid.uuid4().hex[:8]}"}}


def _init_state():
    return {"query": "工伤赔偿怎么计算", "messages": [HumanMessage(content="工伤赔偿怎么计算")]}


def _ai_messages(result):
    return [m for m in result["messages"] if isinstance(m, AIMessage)]


# ── 质量门控三路径 ──

async def test_gate_pass_first_try(monkeypatch, workflow):
    patch_common(monkeypatch, workflow)
    stream_calls, reflect_calls = [], []
    monkeypatch.setattr(workflow.qa_agent, "stream_answer",
                        make_stream_stub(["最终回答"], stream_calls))
    monkeypatch.setattr(workflow.qa_agent, "reflect_answer",
                        make_reflect_stub([make_verdict(True, 0.9)], reflect_calls))

    result = await build(workflow).ainvoke(_init_state(), config=_config())

    assert result["response"] == "最终回答"
    assert len(stream_calls) == 1                     # 没有重试
    assert [m.content for m in _ai_messages(result)] == ["最终回答"]
    assert result["reflection_passed"] is True
    assert result["reflection_feedback"] == ""        # 放行时反馈被清理


async def test_gate_retry_injects_feedback_and_draft_not_in_history(monkeypatch, workflow):
    """核心卖点测试：重试轮注入反馈 + 草稿永不写入对话历史"""
    patch_common(monkeypatch, workflow)
    stream_calls, reflect_calls = [], []
    monkeypatch.setattr(workflow.qa_agent, "stream_answer",
                        make_stream_stub(["草稿v1", "修正v2"], stream_calls))
    monkeypatch.setattr(workflow.qa_agent, "reflect_answer",
                        make_reflect_stub(
                            [make_verdict(False, 0.4, "回答编造了法条条文"),
                             make_verdict(True, 0.9)], reflect_calls))

    result = await build(workflow).ainvoke(_init_state(), config=_config())

    # 重试发生且反馈被注入到第二流的 prompt
    assert len(stream_calls) == 2
    assert stream_calls[0]["reflection_feedback"] == ""
    assert stream_calls[1]["reflection_feedback"] == "回答编造了法条条文"
    # 最终响应是修正版
    assert result["response"] == "修正v2"
    assert result["reflection_round"] == 1
    # 草稿不入历史：对话里只有最终版一条 AI 消息
    assert [m.content for m in _ai_messages(result)] == ["修正v2"]
    assert all("草稿v1" not in m.content for m in result["messages"])


async def test_gate_retry_exhausted_releases_anyway(monkeypatch, workflow):
    """重试额度用尽 → 门控让步放行（答案总得给用户）"""
    patch_common(monkeypatch, workflow)
    monkeypatch.setattr(wf.settings, "REFLECTION_MAX_ROUNDS", 1)
    stream_calls, reflect_calls = [], []
    monkeypatch.setattr(workflow.qa_agent, "stream_answer",
                        make_stream_stub(["草稿v1", "修正v2"], stream_calls))

    async def always_fail(response, cases, query):
        reflect_calls.append(response)
        return make_verdict(False, 0.3, "还是不行")
    monkeypatch.setattr(workflow.qa_agent, "reflect_answer", always_fail)

    result = await build(workflow).ainvoke(_init_state(), config=_config())

    assert len(stream_calls) == 2                     # 1 次原始 + 1 次重试，然后放行
    assert result["response"] == "修正v2"
    assert result["reflection_passed"] is True        # 强制放行
    assert result["reflection_round"] == 1
    assert [m.content for m in _ai_messages(result)] == ["修正v2"]


async def test_gate_disabled_passthrough(monkeypatch, workflow):
    """开关关闭 → 直通，不花评审 LLM 调用"""
    patch_common(monkeypatch, workflow)
    monkeypatch.setattr(wf.settings, "REFLECTION_ENABLED", False)
    stream_calls = []
    monkeypatch.setattr(workflow.qa_agent, "stream_answer",
                        make_stream_stub(["直接回答"], stream_calls))

    async def should_not_be_called(response, cases, query):
        raise AssertionError("开关关闭时不应触发评审 LLM")
    monkeypatch.setattr(workflow.qa_agent, "reflect_answer", should_not_be_called)

    result = await build(workflow).ainvoke(_init_state(), config=_config())

    assert result["response"] == "直接回答"
    assert [m.content for m in _ai_messages(result)] == ["直接回答"]


# ── 意图路由 ──

async def test_route_search_skips_qa(monkeypatch, workflow):
    patch_common(monkeypatch, workflow, intent="search")
    stream_calls = []
    monkeypatch.setattr(workflow.qa_agent, "stream_answer",
                        make_stream_stub(["不该被调用"], stream_calls))

    result = await build(workflow).ainvoke(_init_state(), config=_config())

    assert stream_calls == []                          # search 意图不走 qa
    assert result["response"] == json.dumps([dict(FAKE_CASE)], ensure_ascii=False, indent=2)
    assert result["sources"] == ["来源1"]


async def test_route_document(monkeypatch, workflow):
    patch_common(monkeypatch, workflow, intent="document")
    stream_calls = []
    monkeypatch.setattr(workflow.qa_agent, "stream_answer",
                        make_stream_stub(["不该被调用"], stream_calls))

    async def generate(document_type, params, query):
        return {"content": "民事起诉状（正文）", "references": ["法条1"]}
    monkeypatch.setattr(workflow.document_agent, "generate", generate)

    result = await build(workflow).ainvoke(_init_state(), config=_config())

    assert result["response"] == "民事起诉状（正文）"
    assert result["sources"] == ["法条1"]
    assert stream_calls == []


# ── HITL #1：意图确认 interrupt / resume ──

async def test_hitl_interrupt_and_resume(monkeypatch, workflow):
    """低置信度 → interrupt 挂起；resume 注入用户补充 → 走完 qa 路径"""
    patch_common(monkeypatch, workflow, intent="qa", confidence=0.5)  # 低于 0.8 阈值
    stream_calls = []
    monkeypatch.setattr(workflow.qa_agent, "stream_answer",
                        make_stream_stub(["补充后回答"], stream_calls))

    graph = build(workflow)
    config = _config()

    result = await graph.ainvoke(_init_state(), config=config)
    # 图在 check_intent 处挂起，携带确认问题
    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert payload["type"] == "confirm_intent"
    assert payload["confidence"] == 0.5

    # resume：用户补充信息 → 图从挂起点继续
    resumed = await graph.ainvoke(Command(resume="我是工伤，想问赔偿标准"), config=config)

    assert resumed["user_supplement"] == "我是工伤，想问赔偿标准"
    assert resumed["query"].endswith("我是工伤，想问赔偿标准")   # 补充拼进 query
    assert resumed["response"] == "补充后回答"
    assert [m.content for m in _ai_messages(resumed)] == ["补充后回答"]
