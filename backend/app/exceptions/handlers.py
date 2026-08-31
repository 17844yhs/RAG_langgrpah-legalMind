"""全局异常处理器 + TraceId 中间件 —— 所有错误响应的唯一出口

响应格式遵循 RFC 9457 (Problem Details for HTTP APIs)：
- Content-Type: application/problem+json
- 标准字段：type / title / status / detail / instance
- 扩展字段：code（业务错误码，前端逻辑分支用）、traceId（报障查日志用）

设计原则：
- 对外 fail-safe：堆栈、内部路径等敏感信息绝不进响应体，只回 traceId
- 对内 fail-fast：完整堆栈进日志，通过 traceId 与响应体关联
"""

import json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.exceptions.base import AppException
from app.exceptions.codes import ErrorCode
from app.llm.usage_tracker import RequestUsage, trace_id_var, usage_var

logger = logging.getLogger("app.error")

# type 字段：稳定的错误类型 URI（本地无文档站，用 URN 形式）
# 用来构造一个稳定的错误类型标识符，让前端能区分不同的错误场景
_TYPE_BASE = "urn:problem:legalmind:"

# HTTP 状态码 → RFC 9457 标准短标题
_STATUS_TITLE = {
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
    404: "Not Found", 409: "Conflict", 422: "Unprocessable Entity",
    429: "Too Many Requests", 500: "Internal Server Error",
    502: "Bad Gateway", 503: "Service Unavailable", 504: "Gateway Timeout",
}
# 明确表示这是一个标准化错误响应，而不是普通 JSON 数据。
PROBLEM_MEDIA_TYPE = "application/problem+json"


def _trace_id(request: Request) -> str | None:
    return getattr(request.state, "trace_id", None)


def _problem(request: Request, status: int, code: str, detail: str, **ext) -> dict:
    """构造 RFC 9457 问题详情响应体"""
    body = {
        "type": f"{_TYPE_BASE}{code}",
        "title": _STATUS_TITLE.get(status, "Error"),
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "code": code,                    # 扩展字段：程序分支用
        "traceId": _trace_id(request),   # 扩展字段：用户报障 → 日志一键定位
    }
    body.update(ext)
    return body


def sse_error_event(code: str, detail: str, trace_id: str | None) -> str:
    """SSE 流的错误通道：HTTP 状态码已定（200），错误只能在流内以约定事件传递"""
    payload = {"error": {"code": code, "detail": detail, "traceId": trace_id}}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def register_exception_handlers(app: FastAPI) -> None:
    """在 main.py 中调用一次，注册全局异常处理器"""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        # 业务异常是"预期内的失败"，WARNING 即可，不污染 ERROR 告警
        logger.warning(
            "[%s] %s %s -> %s: %s",
            _trace_id(request), request.method, request.url.path,
            exc.code, exc.detail,
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=_problem(request, exc.http_status, exc.code.value, exc.detail),
            media_type=PROBLEM_MEDIA_TYPE,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # 参数校验失败用 400（422 语义留给业务规则校验）
        # 只保留 loc/msg/type，丢弃 ctx（可能含不可 JSON 序列化的异常对象）
        errors = [
            {
                "field": ".".join(str(loc) for loc in e.get("loc", [])),
                "message": e.get("msg", ""),
                "type": e.get("type", ""),
            }
            for e in exc.errors()[:20]
        ]
        return JSONResponse(
            status_code=400,
            content=_problem(request, 400, ErrorCode.SYS_VALIDATION.value,
                             "请求参数错误", errors=errors),
            media_type=PROBLEM_MEDIA_TYPE,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # 框架自身抛的 404（路由不存在）/405 等，同样拉齐到 Problem Details 格式
        detail = exc.detail if isinstance(exc.detail, str) else _STATUS_TITLE.get(exc.status_code, "Error")
        return JSONResponse(
            status_code=exc.status_code,
            content=_problem(request, exc.status_code, f"HTTP_{exc.status_code}", detail),
            headers=exc.headers,
            media_type=PROBLEM_MEDIA_TYPE,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # 兜底：完整堆栈只进日志（可能含 DB 连接串/模型路径），对外只回 traceId
        logger.exception("[%s] %s %s 未捕获异常", _trace_id(request),
                         request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_problem(request, 500, ErrorCode.SYS_INTERNAL.value, "服务器内部错误"),
            media_type=PROBLEM_MEDIA_TYPE,
        )


class TraceIdMiddleware:
    """纯 ASGI 中间件：为每个请求生成/透传 traceId。

    用纯 ASGI 而非 @app.middleware("http")（BaseHTTPMiddleware）：
    BaseHTTPMiddleware 会破坏 SSE 长连接的客户端断连检测，
    本项目聊天/文书都是流式端点，必须用零侵入的纯 ASGI 实现。

    注意：未捕获异常的 500 响应由更外层的 ServerErrorMiddleware 发出，
    不经过本中间件的 send_wrapper，因此该场景响应头无 X-Request-ID，
    但错误体（problem+json）中的 traceId 不受影响。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 优先透传上游（网关/前端）带来的 X-Request-ID，便于跨服务串联
        trace_id = None
        for key, value in scope.get("headers", []):
            if key == b"x-request-id":
                trace_id = value.decode("latin-1")
                break
        if not trace_id:
            trace_id = uuid.uuid4().hex[:12]

        # 写入 scope.state，后续 request.state.trace_id 可直接读
        scope.setdefault("state", {})["trace_id"] = trace_id
        # 同时写入 ContextVar：langchain 回调（TokenUsageHandler）在
        # asyncio 同一调用链内可直接读到，与 scope 无关
        trace_id_var.set(trace_id)
        # 请求级 token 累计器：handler 在 on_llm_end 里累加，SSE 结束时随
        # usage 事件发给前端；非 LLM 请求为 0 调用，无副作用
        usage_var.set(RequestUsage())

        start = time.perf_counter()
        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", []).append(
                    (b"x-request-id", trace_id.encode("latin-1"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            logger.info(
                "[%s] %s %s -> %s (%.1fms)",
                trace_id, scope.get("method", "?"), scope.get("path", "?"),
                status_code if status_code else "ERR",
                (time.perf_counter() - start) * 1000,
            )
# 一句话：这个中间件在 FastAPI 的最外层，给每个请求发一个“身份证号”（traceId），响应时也把这个号带回去，方便前后端协作排查问题。