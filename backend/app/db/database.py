"""数据库连接管理 - Tortoise ORM"""
from tortoise import Tortoise

from app.config import settings

async def init_db():
    db_url = settings.DATABASE_URL
    # 调试：打印原始和转换后的 URL
    print(f"原始 DATABASE_URL: {db_url}")
    # Tortoise 使用 postgres:// 格式，而 .env 里写的是 postgresql://
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgres://")
    print(f"转换后的 db_url: {db_url}")
    await Tortoise.init(
        db_url=db_url,
        modules={
            "models":[
                "app.models.user",
                "app.models.case",
                "app.models.chat",
                "app.models.document"
            ]
        },
        _enable_global_fallback=True, # 兼容 Windows
        use_tz=False,  # Windows 下不设置时区避免报错
    )
    await Tortoise.generate_schemas(safe=True) # safe=True 避免重复创建表报错

async def close_db():
    await Tortoise.close_connections()

if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())