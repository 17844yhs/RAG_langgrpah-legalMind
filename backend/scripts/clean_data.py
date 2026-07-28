"""清理 PostgreSQL 中的旧数据（laws, cases, eval_samples, eval_runs, eval_results）

用法：cd backend && uv run scripts/clean_data.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def clean():
    from tortoise import Tortoise

    db_url = "postgres://legal_user:legal_pass@localhost:5432/legal_db"
    await Tortoise.init(
        db_url=db_url,
        modules={
            "models": [
                "app.models.case",
                "app.models.law",
                "app.models.eval_dataset",
            ]
        },
        _enable_global_fallback=True,
        use_tz=False,
    )

    from app.models.law import Law
    from app.models.case import Case
    from app.models.eval_dataset import EvalSample, EvalRun, EvalResult

    # 按外键依赖顺序删除
    n = await EvalResult.all().delete()
    print(f"  EvalResult: 删除 {n} 条")
    n = await EvalRun.all().delete()
    print(f"  EvalRun: 删除 {n} 条")
    n = await EvalSample.all().delete()
    print(f"  EvalSample: 删除 {n} 条")
    n = await Case.all().delete()
    print(f"  Case: 删除 {n} 条")
    n = await Law.all().delete()
    print(f"  Law: 删除 {n} 条")

    await Tortoise.close_connections()


if __name__ == "__main__":
    print("🗑️  清理 PostgreSQL 数据...")
    asyncio.run(clean())
    print("✅ 清理完成")
