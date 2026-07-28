"""将 legal_eval_dataset.json 中的法律法规和评估样本导入 PostgreSQL

用法：cd backend && uv run scripts/import_eval_data.py [--data data/legal_eval_dataset_v2.json]
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "legal_eval_dataset_v2.json")


async def import_data(data_file: str = DEFAULT_DATA_FILE):
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
    await Tortoise.generate_schemas(safe=True)

    from app.models.law import Law
    from app.models.case import Case
    from app.models.eval_dataset import EvalSample

    # 读取 JSON
    print(f"  数据文件：{data_file}")
    with open(data_file, encoding="utf-8") as f:
        data = json.load(f)

    # ── 1. 导入法律法规 ──
    laws = data.get("laws", [])
    law_count = 0
    for law in laws:
        _, created = await Law.get_or_create(
            id=law["id"],
            defaults={
                "title": law["title"],
                "content": law["content"],
                "source": law.get("source"),
                "category": law.get("metadata", {}).get("category"),
                "keywords": law.get("metadata", {}).get("keywords"),
            },
        )
        if created:
            law_count += 1
    print(f"  法律法规：新增 {law_count} 条（共 {len(laws)} 条）")

    # ── 2. 导入案例（如果 Case 表中还没有） ──
    cases = data.get("cases", [])
    case_count = 0
    for case in cases:
        # 用 case_number 做去重
        case_number = case.get("case_number")
        if not case_number:
            continue
        existing = await Case.filter(case_number=case_number).first()
        if not existing:
            await Case.create(
                title=case.get("title", ""),
                case_number=case_number,
                court=case.get("court"),
                case_type=case.get("case_type"),
                summary=case.get("summary"),
                content=case.get("content", ""),
                laws=case.get("laws"),
            )
            case_count += 1
    print(f"  案例：新增 {case_count} 条（共 {len(cases)} 条）")

    # ── 3. 导入评估样本 ──
    eval_dataset = data.get("eval_dataset", [])
    sample_count = 0
    for sample in eval_dataset:
        _, created = await EvalSample.get_or_create(
            id=sample["id"],
            defaults={
                "question": sample["question"],
                "ground_truth": sample["ground_truth_answer"],
                "category": sample.get("metadata", {}).get("category"),
                "difficulty": sample.get("metadata", {}).get("difficulty"),
                "relevant_law_ids": sample.get("relevant_law_ids", []),
                "relevant_case_ids": sample.get("relevant_case_ids", []),
            },
        )
        if created:
            sample_count += 1
    print(f"  评估样本：新增 {sample_count} 条（共 {len(eval_dataset)} 条）")

    # ── 统计 ──
    total_laws = await Law.all().count()
    total_cases = await Case.all().count()
    total_samples = await EvalSample.all().count()
    print(f"\n数据库现有：{total_laws} 条法条 / {total_cases} 条案例 / {total_samples} 条评估样本")

    await Tortoise.close_connections()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导入评估数据到 PostgreSQL")
    parser.add_argument("--data", default=DEFAULT_DATA_FILE, help="数据文件路径（默认 legal_eval_dataset.json）")
    args = parser.parse_args()

    print("📥 开始导入评估数据到 PostgreSQL...")
    asyncio.run(import_data(args.data))
    print("✅ 导入完成")
