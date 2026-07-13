'''
"langgraph-checkpoint-postgres>=3.1" "psycopg[binary,pool]>=3.3"

LangGraph 对话记忆持久化（checkpointer）
使用 AsyncPostgresSaver 将对话状态按 thread_id 持久化到 PostgreSQL，
实现跨轮次、跨进程重启的对话记忆。
'''

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import settings

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None

async def init_checkpointer() -> AsyncPostgresSaver:
    """初始化 checkpointer：创建连接池 + 幂等建表。在 lifespan startup 调用。"""
    global _pool, _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    _pool = AsyncConnectionPool(
        conninfo=settings.DATABASE_URL,
        max_size=20,
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
    if _checkpointer is  None:
        raise RuntimeError(
            "Checkpointer 尚未初始化，请在应用启动时调用 init_checkpointer()"
        )
    return _checkpointer

async def close_checkpointer() -> None:
    """关闭连接池。在 lifespan shutdown 调用。"""
    global _pool, _checkpointer
    if _pool is not None:
        await _pool.close()
    _pool = None
    _checkpointer = None