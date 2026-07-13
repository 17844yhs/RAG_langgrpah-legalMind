"""FastAPI 应用主入口"""
import sys
import asyncio
from contextlib import asynccontextmanager


# Windows 上 psycopg（AsyncPostgresSaver）的 async 模式需要 SelectorEventLoop。
# uvicorn 在 Windows 默认通过 loop_factory 使用 ProactorEventLoop——而 loop_factory
# 优先于全局 event_loop_policy，故仅设 policy 无效。这里直接 patch uvicorn 的
# loop factory 强制返回 SelectorEventLoop。本模块在 uvicorn Config.load() 阶段被
# import，早于 Server.run() 的 get_loop_factory()，时机满足（reload 子进程同理）。
if sys.platform == "win32":
    try:
        import uvicorn.loops.asyncio as _uvicorn_aio
        _uvicorn_aio.asyncio_loop_factory = lambda use_subprocess=False: asyncio.SelectorEventLoop()
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
