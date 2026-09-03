"""API 集成测试：健康检查 + RFC 9457 错误契约（黑盒）

验证的是 HTTP 契约：状态码、响应格式、traceId 中间件——不看内部实现。
"""
from tests.api.conftest import parse_sse  # noqa: F401  (conftest 亦可直接用)


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"


async def test_trace_id_middleware_sets_header(client):
    """TraceId 中间件：每个响应都应携带 X-Request-ID（排查链路用）"""
    resp = await client.get("/health")
    assert resp.headers.get("x-request-id")


async def test_unknown_route_returns_problem_details(client):
    """框架 404 也拉齐到 RFC 9457 格式（不再裸 {"detail": "Not Found"}）"""
    resp = await client.get("/api/not/exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    for field in ("type", "title", "status", "detail", "instance", "code"):
        assert field in body
    assert body["status"] == 404
    assert body["instance"] == "/api/not/exist"
    assert body["traceId"]  # 中间件已注入


async def test_validation_error_returns_400_with_fields(client):
    """参数校验失败 → 400（不是 FastAPI 默认 422）+ errors 扩展字段"""
    resp = await client.post("/api/auth/register", json={"username": "x"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "SYS_002"
    assert body["status"] == 400
    assert isinstance(body["errors"], list) and body["errors"]
    missing_fields = {e["field"] for e in body["errors"]}
    # pydantic v2 的 loc 带 body. 前缀（请求体字段）
    assert {"body.email", "body.password"} <= missing_fields


async def test_sse_endpoint_validation(client, auth_headers):
    """流式端点的参数校验同样走 400（空消息违反 min_length）"""
    resp = await client.post("/api/chat/stream", headers=auth_headers, json={"message": ""})
    assert resp.status_code == 400
    assert resp.json()["code"] == "SYS_002"
