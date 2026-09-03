"""单元测试：异常体系 — 错误码注册表 + RFC 9457 问题详情构造

测试定位：单元级白盒。这里最关键的是"注册表完整性"测试——
项目约定：新增错误只加注册表映射，全局异常处理器代码不动。
这个约定靠人自觉守不住，所以用 set(ErrorCode) == set(_CODE_META) 让机器守：
谁加了错误码忘了配映射，测试立刻红。
"""
import json

from starlette.requests import Request

from app.exceptions.base import AppException, AuthError, ChatError
from app.exceptions.codes import ErrorCode, _CODE_META
from app.exceptions.handlers import _problem, sse_error_event


# ── 注册表完整性 ──

def test_every_error_code_has_meta():
    """每个 ErrorCode 必须在 _CODE_META 里有 (status, detail) 映射——防止漏注册"""
    assert set(_CODE_META.keys()) == set(ErrorCode)


def test_meta_status_codes_are_valid_http():
    for status, detail in _CODE_META.values():
        assert 400 <= status <= 599
        assert detail, f"{status} 的默认文案不能为空"


# ── AppException 行为 ──

def test_app_exception_uses_registry_defaults():
    exc = AppException(ErrorCode.CHAT_SESSION_NOT_FOUND)
    assert exc.code == ErrorCode.CHAT_SESSION_NOT_FOUND
    assert exc.http_status == 404
    assert exc.detail == "会话不存在"


def test_app_exception_overrides():
    exc = AuthError(ErrorCode.AUTH_USERNAME_TAKEN, detail="用户名小明已存在")
    assert exc.http_status == 400                    # 状态码来自注册表
    assert exc.detail == "用户名小明已存在"            # 文案可覆盖


def test_app_exception_is_exception():
    exc = ChatError(ErrorCode.SYS_INTERNAL)
    assert isinstance(exc, Exception)
    assert str(exc) == exc.detail


# ── RFC 9457 问题详情 ──

def _fake_request(path: str = "/api/chat/stream") -> Request:
    req = Request({"type": "http", "method": "POST", "path": path,
                   "headers": [], "query_string": b""})
    req.state.trace_id = "trace-abc"
    return req


def test_problem_contains_all_standard_fields():
    body = _problem(_fake_request(), 404, "CASE_001", "没有找到这个案例")
    for field in ("type", "title", "status", "detail", "instance"):
        assert field in body
    # 项目约定的扩展字段
    assert body["code"] == "CASE_001"
    assert body["traceId"] == "trace-abc"
    assert body["status"] == 404
    assert body["instance"] == "/api/chat/stream"
    assert body["type"].endswith("CASE_001")


def test_problem_trace_id_optional():
    req = Request({"type": "http", "method": "GET", "path": "/x", "headers": [], "query_string": b""})
    body = _problem(req, 500, "SYS_001", "boom")
    assert body["traceId"] is None


def test_sse_error_event_format():
    raw = sse_error_event("RAG_001", "检索失败", "trace-1")
    assert raw.startswith("data: ") and raw.endswith("\n\n")
    payload = json.loads(raw.removeprefix("data: "))
    assert payload == {"error": {"code": "RAG_001", "detail": "检索失败", "traceId": "trace-1"}}
