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


def _redis_sync():
    """测试用同步 Redis 客户端（与 app 同款 RESP2 配置）"""
    import redis as redis_sync
    return redis_sync.Redis.from_url(settings.REDIS_URL,
                                     socket_connect_timeout=1.0, protocol=2)


@pytest.fixture(autouse=True)
def _fresh_captcha_client():
    """每测重置验证码模块的懒加载客户端：模块级缓存的 aioredis 连接绑定创建时
    的 event loop，pytest-asyncio 每测新建 loop，不复位会报 Event loop is closed
    （生产单 loop 常驻无此问题，纯测试环境适配）"""
    from app.utils import captcha as captcha_mod
    captcha_mod._state["client"] = None
    yield
    captcha_mod._state["client"] = None


@pytest.fixture
def redis_available():
    """Redis 不可达时跳过验证码相关测试（验证码 fail-closed，必须真 Redis）"""
    try:
        _redis_sync().ping()
    except Exception:
        pytest.skip("Redis 不可达，跳过验证码相关测试")
    yield


async def _new_captcha(client):
    """领一题真验证码：走真实 /captcha 端点，答案从 Redis 读（等价于人工识图）"""
    resp = await client.get("/api/v1/auth/captcha")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    code = _redis_sync().get(f"captcha:{body['captcha_id']}")
    assert code, "验证码未落 Redis"
    return {"captcha_id": body["captcha_id"], "captcha_code": code.decode()}


@pytest.fixture
def get_captcha(redis_available):
    """领题协程函数：pair = await get_captcha(client)——一测多题时直接多次调用"""
    return _new_captcha


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
    # 长期记忆 Store（14.3）依赖 checkpointer 连接池，同步跳过——
    # lifespan 里 init_store() 在池未初始化时会抛 RuntimeError
    monkeypatch.setattr(main_mod, "init_store", _noop)
    # 预热会加载 cross-encoder 并做真实推理（秒级~30s），函数级夹具逐测试触发
    # lifespan，不跳过会让每个 API 测试都白付一次模型加载
    monkeypatch.setattr(main_mod, "_prewarm_retrieval", _noop)

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
async def auth_headers(client: httpx.AsyncClient, redis_available):
    """注册并登录一个随机用户，返回 Bearer 认证头（注册/登录均需验证码）"""
    import uuid
    creds = {
        "username": f"u{uuid.uuid4().hex[:8]}",
        "email": f"{uuid.uuid4().hex[:8]}@test.com",
        "password": "Passw0rd!",
    }
    resp = await client.post("/api/v1/auth/register",
                             json={**creds, **(await _new_captcha(client))})
    assert resp.status_code == 200, resp.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": creds["username"], "password": creds["password"],
              **(await _new_captcha(client))})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}
