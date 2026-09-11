"""导出评测集快照 JSON（与 EvalSample 表同步，供离线查看/导入）"""
import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))


async def main():
    from tortoise import Tortoise
    await Tortoise.init(
        db_url="postgres://legal_user:legal_pass@localhost:5432/legal_db",
        modules={"models": ["app.models.law", "app.models.case", "app.models.eval_dataset"]},
    )
    from app.models.eval_dataset import EvalSample
    from app.models.case import Case
    from app.models.law import Law

    samples = await EvalSample.all().order_by("id")
    law_total = await Law.all().count()
    case_total = await Case.all().count()

    snapshot = {
        "version": "3.0",
        "created_at": datetime.now().isoformat(),
        "statistics": {
            "total_laws": law_total,
            "total_cases": case_total,
            "total_qas": len(samples),
            "scene_law_qas": sum(1 for s in samples if s.relevant_law_ids and s.difficulty in ("易", "中", "难") and not s.relevant_case_ids),
            "case_fact_qas": sum(1 for s in samples if s.relevant_case_ids),
        },
        "samples": [s.to_dict() for s in samples],
    }
    out = os.path.join(os.path.dirname(__file__), '..', 'data', 'legal_eval_dataset_v3.json')
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"快照已导出: {os.path.abspath(out)}")
    print(f"统计: {snapshot['statistics']}")
    await Tortoise.close_connections()


asyncio.run(main())
