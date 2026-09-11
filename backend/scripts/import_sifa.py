"""司法解释补充导入：高频司法解释按条粒度入库（复用 enrich_legal_data 的解析逻辑）"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

from scripts.enrich_legal_data import fetch_repo_file, split_articles


# (司法解释文件名, 显示名, category)
SIFA_SOURCES = [
    ("最高人民法院关于审理民间借贷案件适用法律若干问题的规定(2020-12-29).md", "最高人民法院关于审理民间借贷案件适用法律若干问题的规定", "借贷"),
    ("最高人民法院关于适用《民法典》婚姻家庭编的解释（一）(2020-12-29).md", "最高人民法院关于适用《民法典》婚姻家庭编的解释（一）", "婚姻家庭"),
    ("最高人民法院关于适用《民法典》婚姻家庭编的解释（二）(2025-01-15).md", "最高人民法院关于适用《民法典》婚姻家庭编的解释（二）", "婚姻家庭"),
    ("最高人民法院关于审理人身损害赔偿案件适用法律若干问题的解释(2022-04-24).md", "最高人民法院关于审理人身损害赔偿案件适用法律若干问题的解释", "侵权"),
    ("最高人民法院关于审理劳动争议案件适用法律问题的解释（一）(2020-12-29).md", "最高人民法院关于审理劳动争议案件适用法律问题的解释（一）", "劳动"),
    ("最高人民法院关于审理劳动争议案件适用法律问题的解释（二）(2025-07-31).md", "最高人民法院关于审理劳动争议案件适用法律问题的解释（二）", "劳动"),
    ("最高人民法院关于审理建设工程施工合同纠纷案件适用法律问题的解释（一）(2020-12-29).md", "最高人民法院关于审理建设工程施工合同纠纷案件适用法律问题的解释（一）", "合同"),
    ("最高人民法院关于审理物业服务纠纷案件适用法律若干问题的解释(2020-12-29).md", "最高人民法院关于审理物业服务纠纷案件适用法律若干问题的解释", "物业"),
    ("最高人民法院关于审理道路交通事故损害赔偿案件适用法律若干问题的解释(2020-12-29).md", "最高人民法院关于审理道路交通事故损害赔偿案件适用法律若干问题的解释", "交通"),
    ("最高人民法院关于适用《民法典》合同编通则若干问题的解释(2023-12-04).md", "最高人民法院关于适用《民法典》合同编通则若干问题的解释", "合同"),
    ("最高人民法院关于适用《民法典》有关担保制度的解释(2020-12-31).md", "最高人民法院关于适用《民法典》有关担保制度的解释", "担保"),
    ("最高人民法院关于确定民事侵权精神损害赔偿责任若干问题的解释(2020-12-29).md", "最高人民法院关于确定民事侵权精神损害赔偿责任若干问题的解释", "侵权"),
    ("最高人民法院关于适用《民法典》侵权责任编的解释（一）(2024-09-25).md", "最高人民法院关于适用《民法典》侵权责任编的解释（一）", "侵权"),
    ("最高人民法院关于适用《民法典》总则编若干问题的解释(2022-02-24).md", "最高人民法院关于适用《民法典》总则编若干问题的解释", "民法总则"),
    ("最高人民法院关于审理工伤保险行政案件若干问题的规定(2014-06-18).md", "最高人民法院关于审理工伤保险行政案件若干问题的规定", "劳动"),
    ("最高人民法院关于审理商品房买卖合同纠纷案件适用法律若干问题的解释(2020-12-29).md", "最高人民法院关于审理商品房买卖合同纠纷案件适用法律若干问题的解释", "合同"),
    ("最高人民法院关于审理医疗损害责任纠纷案件适用法律若干问题的解释(2020-12-29).md", "最高人民法院关于审理医疗损害责任纠纷案件适用法律若干问题的解释", "医疗"),
    ("最高人民法院关于适用《民法典》物权编的解释（一）(2020-12-29).md", "最高人民法院关于适用《民法典》物权编的解释（一）", "物权"),
]


async def main():
    from tortoise import Tortoise
    from app.models.law import Law

    await Tortoise.init(
        db_url="postgres://legal_user:legal_pass@localhost:5432/legal_db",
        modules={"models": ["app.models.law"]},
    )
    # 找最大 law_id 序号续接
    last = await Law.filter(id__startswith="law_").order_by("-id").first()
    seq = max(int(last.id.split("_")[1]) + 1, 3600) if last else 3600

    total = 0
    for fname, display, category in SIFA_SOURCES:
        md = fetch_repo_file(f"司法解释/{fname}")
        if md is None:
            print(f"[SKIP] {display}")
            continue
        articles = split_articles(md)
        if not articles:
            print(f"[WARN] {display}: 0 条（格式不符？）")
            continue
        batch = [
            Law(
                id=f"law_{seq + i}",
                title=f"{display} {art_no}",
                content=body,
                source=f"LawRefBook/Laws 司法解释/{fname}",
                category=category,
                keywords=[display, category],
            )
            for i, (art_no, body) in enumerate(articles)
        ]
        seq += len(batch)
        await Law.bulk_create(batch, ignore_conflicts=True)
        total += len(batch)
        print(f"[OK] {display}: {len(articles)} 条")
        time.sleep(0.6)

    print(f"司法解释导入完成: {total} 条")
    await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
