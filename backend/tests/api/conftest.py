"""API 集成测试公共夹具

┌─────────────────────────── 测试定位（复习笔记）───────────────────────────┐
│ 级别：集成（httpx 打真实的 FastAPI 路由 + 中间件 + 异常处理器 + ORM）       │
│ 方法：黑盒为主（从 HTTP 接口喂请求、验响应），例外是 token 落库时翻         │
│       数据库验证 JSONB —— 那一小块是灰盒                                   │
│ 手段：独立的 legal_db_test 测试库（每个测试重建，互不污染）；               │
│       workflow 换 Fake（chat 流式端点的 LLM 依赖）                         │
│ 与图逻辑测试的分工：那边测"图内部"，这里测"HTTP 契约"——                    │
│ 状态码、RFC 9457 格式、SSE 事件序列、认证链路                              │
└──────────────────────────────────────────────────────────────────────────┘
"""
import asyncio
import os
from urllib.parse import urlsplit

import asyncpg
import httpx
import pytest

# Windows 下 asyncpg/psycopg 要求 Selector 事件循环（conftest 顶层已设，这里兜底）

from app.config import settings


@pytest.fixture
def pg_available():
    """PG 不可达时跳过全部 API 测试（CI 无数据库容器时不挂掉）"""
    u = urlsplit(settings.DATABASE_URL)
    try:
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            _probe(u.hostname, u.port or 5432, u.username, u.password))
    except Exception:
        pytest.skip("PostgreSQL 不可达，跳过 API 集成测试", allow_module_level=False)
    yield


async def _probe(host, port, user, password):
    conn = await asyncpg.connect(host=host, port=port, user=user,
                                 password=password, database="postgres")
    await conn.close()


@pytest.fixture
async def client(pg_available, monkeypatch):
    """httpx 异步客户端：独立测试库 + 精简 lifespan（跳过向量库/检查点）"""
    u = urlsplit(settings.DATABASE_URL)
    test_db = "legal_db_test"

    # 1. 重建独立测试库（与开发库 legal_db 完全隔离）
    conn = await asyncpg.connect(host=u.hostname, port=u.port or 5432,
                                 user=u.username, password=u.password,
                                 database="postgres")
    try:
        await conn.execute(f"DROP DATABASE IF EXISTS {test_db} WITH (FORCE)")
        await conn.execute(f"CREATE DATABASE {test_db}")
    finally:
        await conn.close()

    # 2. lifespan 换库：只 patch 配置 dict 的连接项（init_db 读它），
    #    向量库/检查点不需要（HTTP 契约测试不涉及 RAG 与 checkpoint）
    import app.db.database as db_mod
    monkeypatch.setitem(db_mod.TORTOISE_ORM["connections"], "default",
                        f"postgres://{u.username}:{u.password}@{u.hostname}:{u.port or 5432}/{test_db}")

    import app.main as main_mod

    async def _noop():
        return None
    monkeypatch.setattr(main_mod, "init_vector_store", _noop)
    monkeypatch.setattr(main_mod, "init_checkpointer", _noop)

    # 3. 手动驱动 lifespan（ASGITransport 不自动执行 lifespan），启动 Tortoise
    async with main_mod.app.router.lifespan_context(main_mod.app):
        transport = httpx.ASGITransport(app=main_mod.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://test") as c:
            yield c


def parse_sse(text: str) -> list[dict]:
    """解析 SSE 响应体 → 事件列表（'data: [DONE]' → {'done': True}）"""
    import json
    events = []
    for line in text.split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line.removeprefix("data: ").strip()
        events.append({"done": True} if payload == "[DONE]"
                      else json.loads(payload))
    return events


@pytest.fixture
async def auth_headers(client: httpx.AsyncClient):
    """注册并登录一个随机用户，返回 Bearer 认证头"""
    import uuid
    creds = {
        "username": f"u{uuid.uuid4().hex[:8]}",
        "email": f"{uuid.uuid4().hex[:8]}@test.com",
        "password": "Passw0rd!",
    }
    resp = await client.post("/api/auth/register", json=creds)
    assert resp.status_code == 200, resp.text
    login = await client.post("/api/auth/login",
                              json={"username": creds["username"],
                                    "password": creds["password"]})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}
