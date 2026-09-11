"""补导特种设备安全法（电梯等特种设备监管，补"电梯困人"类问题缺口）"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

from scripts.enrich_legal_data import fetch_repo_file, split_articles, resolve_filename


async def main():
    from tortoise import Tortoise
    from app.models.law import Law

    await Tortoise.init(
        db_url="postgres://legal_user:legal_pass@localhost:5432/legal_db",
        modules={"models": ["app.models.law"]},
    )
    if await Law.filter(title__startswith="中华人民共和国特种设备安全法").exists():
        print("特种设备安全法已存在，跳过")
        await Tortoise.close_connections()
        return

    fname = resolve_filename("社会法", "特种设备安全法")
    if fname is None:
        await Tortoise.close_connections()
        return
    md = fetch_repo_file(f"社会法/{fname}")
    articles = split_articles(md)
    # 数值化取最大序号续接（order_by("-id") 是字符串排序，law_999 > law_4208 会算错）
    ids = await Law.all().values_list("id", flat=True)
    max_num = max((int(i.split("_")[1]) for i in ids
                   if i.startswith("law_") and i.split("_")[1].isdigit()), default=0)
    seq = max_num + 1

    batch = [
        Law(
            id=f"law_{seq + i}",
            title=f"中华人民共和国特种设备安全法 {art_no}",
            content=body,
            source=f"LawRefBook/Laws 社会法/{fname}",
            category="特种设备",
            keywords=["中华人民共和国特种设备安全法", "特种设备"],
        )
        for i, (art_no, body) in enumerate(articles)
    ]
    await Law.bulk_create(batch, ignore_conflicts=True)
    print(f"[OK] 特种设备安全法: {len(articles)} 条")
    time.sleep(0.3)
    await Tortoise.close_connections()


asyncio.run(main())
