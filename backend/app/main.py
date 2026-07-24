"""FastAPI 应用主入口"""
import sys
import asyncio
from contextlib import asynccontextmanager


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

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import init_db,close_db
from app.rag.vector_store import init_vector_store
from app.llm.checkpoint import init_checkpointer,close_checkpointer

@asynccontextmanager
async def lifespan(app:FastAPI):
    """应用生命周期：启动时连数据库，关闭时断开"""
    await init_db()
    await init_vector_store()
    await init_checkpointer()
    yield
    await close_db()
    await close_checkpointer()

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

from app.api import auth,chat,documents,cases
app.include_router(auth.router,prefix="/api/auth",tags=["认证"])
app.include_router(chat.router, prefix="/api/chat", tags=["聊天"])
app.include_router(documents.router, prefix="/api/documents", tags=["文书"])
app.include_router(cases.router, prefix="/api/cases", tags=["案例"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

'''
uv run uvicorn app.main:app --port 8000
'''
