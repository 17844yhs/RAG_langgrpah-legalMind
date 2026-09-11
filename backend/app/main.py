"""FastAPI 应用主入口"""
import os
import sys
import asyncio
import logging
from contextlib import asynccontextmanager

from app.config import settings

# uvicorn 只配置自己的 logger，root logger 需要这里兜底，
# 否则 app.* 的业务日志（如全局异常处理器的堆栈日志）不会输出
logging.basicConfig(level=logging.INFO)

# ── LangSmith 追踪注入 ──────────────────────────────────
# LangChain 自动追踪检查的是 os.environ，不是 pydantic Settings
# 必须在这里把配置值回写到环境变量，追踪才能真正生效
if settings.LANGSMITH_TRACING:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT


# Windows 上 psycopg（AsyncPostgresSaver）的 async 模式需要 SelectorEventLoop。
# uvicorn 0.49.0 的 get_loop_factory() 存在 bug：它调用 factory 函数后直接返回
# 事件循环对象，而不是返回 factory 函数本身。asyncio_run() 期望 loop_factory 是
# 可调用对象，导致 TypeError。修复方案：设置 SelectorEventLoop 策略，并让
# get_loop_factory() 返回 None，这样 asyncio.Runner 会使用 new_event_loop()
# 创建事件循环，而 new_event_loop() 会遵循全局的 event_loop_policy。
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        from uvicorn.config import Config
        Config.get_loop_factory = lambda self: None
    except ImportError:
        pass


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db,close_db
from app.rag.vector_store import init_vector_store
from app.llm.checkpoint import init_checkpointer,close_checkpointer
from app.cache.redis_cache import ping_cache, close_cache
from app.exceptions.handlers import register_exception_handlers, TraceIdMiddleware

logger = logging.getLogger("app.main")


async def _prewarm_retrieval():
    """启动时预热检索链路（嵌入 + BM25 索引 + cross-encoder）+ 首次推理。

    RetrievalAgent 是懒加载单例：不预热的话，第一个请求要额外承担
    秒级~30s 的模型加载和 torch 首次推理初始化（内核自 tuning）。
    把成本移到启动阶段，服务器就绪即可全速服务。
    加载是同步 CPU 密集操作，扔线程池不阻塞事件循环；
    失败仅记日志不阻断启动——首个请求会走原懒加载路径兜底。
    """
    import time
    from app.agents.retrieval_agent import get_retrieval_agent

    t0 = time.perf_counter()
    try:
        agent = await asyncio.to_thread(get_retrieval_agent)
        # 一次端到端小检索：触发嵌入/BM25/rerank 的首次推理初始化
        await agent.retrieve("预热查询", top_k=2)
        logger.info("检索链路预热完成，耗时 %.1fs", time.perf_counter() - t0)
    except Exception:
        logger.exception("检索链路预热失败（首个请求将懒加载兜底）")


@asynccontextmanager
async def lifespan(app:FastAPI):
    """应用生命周期：启动时连数据库，关闭时断开"""
    # 安全哨兵：默认 JWT 密钥 = 任何人都能伪造 token，生产环境必须显式配置
    if settings.SECRET_KEY == "secret-key":
        logger.warning(
            "SECRET_KEY 仍为默认值 'secret-key'——JWT 可被任意伪造！"
            "请在 .env 中配置强随机密钥（openssl rand -hex 32）"
        )
    await init_db()
    await init_vector_store()
    await init_checkpointer()
    # 缓存探测仅做观测日志：不可达时缓存层自动熔断降级，业务零感知
    if await ping_cache():
        logger.info("Redis 缓存已连接（意图/检索缓存生效）")
    else:
        logger.warning("Redis 不可达或缓存未启用，缓存自动降级直连")
    await _prewarm_retrieval()
    yield
    await close_db()
    await close_checkpointer()
    await close_cache()

app = FastAPI(
    title="LegalMind API",
    description="智能法律咨询系统 API",
    version="1.0.0",
    lifespan=lifespan
)

# 跨域配置，允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局异常处理：所有错误响应统一走 RFC 9457 Problem Details 格式
register_exception_handlers(app)
# traceId 中间件：每个请求生成/透传排查 ID，响应头与错误体都会携带
app.add_middleware(TraceIdMiddleware)

from app.api import auth, chat, documents, cases

# API 版本化前缀：未来不兼容变更可并存 /api/v2，旧客户端不受影响
API_V1_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=f"{API_V1_PREFIX}/auth", tags=["认证"])
app.include_router(chat.router, prefix=f"{API_V1_PREFIX}/chat", tags=["聊天"])
app.include_router(documents.router, prefix=f"{API_V1_PREFIX}/documents", tags=["文书"])
app.include_router(cases.router, prefix=f"{API_V1_PREFIX}/cases", tags=["案例"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

'''
uv run uvicorn app.main:app --port 8000
'''
