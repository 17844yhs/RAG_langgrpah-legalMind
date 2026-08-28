"""数据库连接管理 - Tortoise ORM

迁移：tortoise-orm >= 1.0 内置迁移 CLI（官方对 1.0+ 的建议，替代 Aerich）。
  - 生成迁移：uv run python -m tortoise -c app.db.database.TORTOISE_ORM makemigrations
  - 执行迁移：uv run python -m tortoise -c app.db.database.TORTOISE_ORM migrate
  - 查看历史：uv run python -m tortoise -c app.db.database.TORTOISE_ORM history
存量库基线：首次 makemigrations 生成的全量迁移用 `migrate --fake` 登记
（库已由 generate_schemas 建好，只记状态不执行 SQL），此后变更走正常流程。
"""
from tortoise import Tortoise

from app.config import settings

MODEL_MODULES = [
    "app.models.user",
    "app.models.case",
    "app.models.chat",
    "app.models.document",
    "app.models.law",
    "app.models.eval_dataset",
]


def _tortoise_db_url() -> str:
    """Tortoise 使用 postgres:// 格式，而 .env 里写的是 postgresql://"""
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgres://")
    return db_url


# 标准 config dict：运行时 init 与迁移 CLI 共用的单一配置来源
TORTOISE_ORM = {
    "connections": {
        "default": _tortoise_db_url(),
    },
    "apps": {
        "models": {
            "models": MODEL_MODULES,
            "migrations": "app.models.migrations",  # 迁移包位置（MigrationLoader 只认显式声明）
            "default_connection": "default",
        },
    },
    "use_tz": False,  # Windows 下不设置时区避免报错
}


async def init_db():
    await Tortoise.init(
        config=TORTOISE_ORM,
        _enable_global_fallback=True,  # 兼容 Windows
    )
    await Tortoise.generate_schemas(safe=True)  # safe=True 避免重复创建表报错
    # 注意：generate_schemas 只建表不改表（增量变更必须走迁移），保留它是为了
    # 新环境首次启动能自动建表；已有环境的结构演进由 migrations/ 接管。


async def close_db():
    await Tortoise.close_connections()

if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())
