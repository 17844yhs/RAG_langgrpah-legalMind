"""插入示例案例数据"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tortoise import Tortoise


async def seed():
    await Tortoise.init(
        db_url="postgres://legal_user:legal_pass@localhost:5432/legal_db",
        modules={"models": ["app.models.case"]},
    )
    from app.models.case import Case

    samples = [
        {
            "title": "张三与李四离婚财产纠纷案",
            "case_number": "（2023）京0105民初12345号",
            "court": "北京市朝阳区人民法院",
            "case_type": "民事",
            "judgment_date": "2023-06-15",
            "summary": "夫妻双方因感情破裂协议离婚，对婚后共同购买的房产分割产生争议。法院判决房产归一方所有，获得房产一方支付另一方房屋折价款。",
            "laws": ["《中华人民共和国民法典》第一千零六十二条", "《中华人民共和国民法典》第一千零八十七条"],
        },
        {
            "title": "王某劳动仲裁案",
            "case_number": "（2022）沪浦劳人仲案字第7890号",
            "court": "上海市浦东新区劳动人事争议仲裁委员会",
            "case_type": "劳动争议",
            "judgment_date": "2022-11-20",
            "summary": "劳动者因公司拖欠工资被迫离职，要求支付经济补偿金。仲裁委员会支持了劳动者的请求，裁决公司支付拖欠工资及经济补偿金。",
            "laws": ["《中华人民共和国劳动合同法》第三十八条", "《中华人民共和国劳动合同法》第四十六条"],
        },
        {
            "title": "李某交通事故赔偿案",
            "case_number": "（2023）粤03民终5678号",
            "court": "深圳市中级人民法院",
            "case_type": "民事",
            "judgment_date": "2023-09-10",
            "summary": "交通事故受害人起诉肇事方及保险公司，要求赔偿医疗费、误工费、残疾赔偿金等。法院判决保险公司在交强险限额内赔偿，超出部分由肇事方承担。",
            "laws": ["《中华人民共和国民法典》第一千一百七十九条", "《中华人民共和国民法典》第一千二百一十三条"],
        },
    ]

    for data in samples:
        # case_number查询存在的参数 -> defaults 创建时才用的数据，查询时别管它们
        _, created = await Case.get_or_create(case_number=data["case_number"], defaults=data)
        status = "新增" if created else "已存在"
        print(f"  {status}: {data['title']}")

    await Tortoise.close_connections()


if __name__ == "__main__":
    print("🌱 开始插入种子数据...")
    asyncio.run(seed())
    print("✅ 种子数据插入完成")

    # zoneinfo._common.ZoneInfoNotFoundError: 'No time zone found with key UTC'