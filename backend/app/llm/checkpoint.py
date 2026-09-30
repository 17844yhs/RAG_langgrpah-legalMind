"""LangGraph 对话记忆持久化（checkpointer）

依赖：langgraph-checkpoint-postgres>=3.1 + psycopg[binary,pool]>=3.3
使用 AsyncPostgresSaver 将对话状态按 thread_id 持久化到 PostgreSQL，
实现跨轮次、跨进程重启的对话记忆（HITL 中断恢复的基础）。
"""

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

from app.config import settings

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None
_store: AsyncPostgresStore | None = None

async def init_checkpointer() -> AsyncPostgresSaver:
    """初始化 checkpointer：创建连接池 + 幂等建表。在 lifespan startup 调用。"""
    global _pool, _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    _pool = AsyncConnectionPool(
        conninfo=settings.DATABASE_URL,
        max_size=settings.DB_POOL_MAX_SIZE,
        open=False,
        kwargs={
            "autocommit": True,  # 确保连接不在事务中，以允许 CREATE INDEX CONCURRENTLY
        },
    )

    await _pool.open()

    _checkpointer = AsyncPostgresSaver(conn=_pool)

    await _checkpointer.setup()
    return _checkpointer

def get_checkpointer() -> AsyncPostgresSaver:
    """获取 checkpointer 单例，供 LangGraph 编译图时使用。

    必须在 init_checkpointer() 之后调用（即在 lifespan 启动完成后），
    否则图编译阶段拿不到 checkpointer。
    """
    if _checkpointer is None:
        raise RuntimeError(
            "Checkpointer 尚未初始化，请在应用启动时调用 init_checkpointer()"
        )
    return _checkpointer


async def init_store() -> AsyncPostgresStore:
    """初始化 LangGraph Store（跨会话长期记忆，14.3 用户主权模式）。

    - 复用 checkpointer 连接池（同一套 PostgreSQL），必须在 init_checkpointer 之后调用
    - setup() 幂等建表（store 表与 checkpoint 表共存一个库）
    - 记忆条目由用户在前端手动维护（非 agent 自动抽取）：
      法律场景 agent 记错事实的代价高于记不住，授权与准确性都由用户背书
    """
    global _store
    if _store is not None:
        return _store
    if _pool is None:
        raise RuntimeError("连接池未初始化：请先调用 init_checkpointer()")
    _store = AsyncPostgresStore(conn=_pool)
    await _store.setup()
    return _store


def get_store() -> AsyncPostgresStore:
    """获取 store 单例：图编译（compile(store=...)）与 /api/memory CRUD 共用。"""
    if _store is None:
        raise RuntimeError(
            "Store 尚未初始化，请在应用启动时调用 init_store()"
        )
    return _store

async def close_checkpointer() -> None:
    """关闭连接池。在 lifespan shutdown 调用。"""
    global _pool, _checkpointer
    if _pool is not None:
        await _pool.close()
    _pool = None
    _checkpointer = None