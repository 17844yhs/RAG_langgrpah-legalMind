"""评测集扩充：场景化问句（独立于条文措辞，消除同源虚高）+ 案例事实型样本

两类样本：
1. 场景问答（SCENE_QA）：手工编写的真实用户问法 → 映射库内法条。
   question 与条文措辞独立（非同源复制），ground_truth = 条文全文
2. 案例事实型（CASE_FACT）：典型案例"基本案情" → question，"裁判结果" → ground_truth

幂等：id 续接现有 qa_XXX 序号；title 映射不到库内法条的样本跳过并打印。
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

from scripts.enrich_legal_data import fetch_repo_file  # noqa: E402

# (问题, 法律title精确前缀, 条号, category, 难度)
SCENE_QA = [
    ("公司一直不和我签书面劳动合同，有什么法律后果？", "中华人民共和国劳动合同法", "第八十二条", "劳动", "中"),
    ("劳动合同的试用期最长不能超过多久？", "中华人民共和国劳动合同法", "第十九条", "劳动", "易"),
    ("公司要求我周末加班我可以拒绝吗？", "中华人民共和国劳动法", "第四十一条", "劳动", "中"),
    ("加班费应该按什么标准支付？", "中华人民共和国劳动法", "第四十四条", "劳动", "易"),
    ("公司拖欠工资我应该怎么办？", "中华人民共和国劳动合同法", "第三十条", "劳动", "易"),
    ("用人单位克扣工资要承担什么责任？", "中华人民共和国劳动法", "第九十一条", "劳动", "中"),
    ("公司裁员的经济补偿是怎么计算的？", "中华人民共和国劳动合同法", "第四十七条", "劳动", "中"),
    ("离婚时夫妻共同财产应该怎么分割？", "中华人民共和国民法典婚姻家庭编", "第一千零八十七条", "婚姻家庭", "易"),
    ("婚前个人财产在离婚时归谁？", "中华人民共和国民法典婚姻家庭编", "第一千零六十三条", "婚姻家庭", "中"),
    ("丈夫欠的赌债妻子要一起还吗？", "中华人民共和国民法典婚姻家庭编", "第一千零六十四条", "婚姻家庭", "中"),
    ("离婚冷静期是多长时间？", "中华人民共和国民法典婚姻家庭编", "第一千零七十七条", "婚姻家庭", "易"),
    ("一方家暴导致离婚，无过错方能要求赔偿吗？", "中华人民共和国民法典婚姻家庭编", "第一千零九十一条", "婚姻家庭", "易"),
    ("被家暴了可以向法院申请人身保护令吗？", "中华人民共和国反家庭暴力法", "第二十三条", "婚姻家庭", "中"),
    ("交通事故中机动车和行人相撞，责任怎么划分？", "中华人民共和国道路交通安全法", "第七十六条", "交通", "易"),
    ("酒驾会被怎么处罚？", "中华人民共和国道路交通安全法", "第九十一条", "交通", "易"),
    ("发生交通事故后逃逸有什么后果？", "中华人民共和国道路交通安全法", "第九十九条", "交通", "中"),
    ("民间借贷利息约定多少受法律保护？", "最高人民法院关于审理民间借贷案件适用法律若干问题的规定", "第二十五条", "借贷", "中"),
    ("别人借我的钱一直不还，诉讼时效是多久？", "中华人民共和国民法典总则编", "第一百八十八条", "民法总则", "易"),
    ("小区电梯发生事故，维保单位要负责吗？", "中华人民共和国特种设备安全法", "第四十五条", "特种设备", "中"),
    ("高空抛物砸到人找不到扔的人怎么办？", "中华人民共和国民法典侵权责任编", "第一千二百五十四条", "侵权", "中"),
    ("楼上漏水把我家淹了，谁来赔偿？", "中华人民共和国民法典侵权责任编", "第一千二百五十三条", "侵权", "中"),
    ("在网上买东西遇到假货，可以要求几倍赔偿？", "中华人民共和国消费者权益保护法", "第五十五条", "消费", "易"),
    ("网购的商品可以七天无理由退货吗？", "中华人民共和国消费者权益保护法", "第二十五条", "消费", "易"),
    ("合同约定的违约金过高法院会支持吗？", "中华人民共和国民法典合同编", "第五百八十五条", "合同", "中"),
    ("定金和违约金可以同时主张吗？", "中华人民共和国民法典合同编", "第五百八十八条", "合同", "中"),
    ("一方不履行合同义务要承担什么责任？", "中华人民共和国民法典合同编", "第五百七十七条", "合同", "易"),
    ("故意伤害他人身体会判多久？", "中华人民共和国刑法", "第二百三十四条", "刑事", "中"),
    ("偷东西会怎么判刑？", "中华人民共和国刑法", "第二百六十四条", "刑事", "中"),
    ("诈骗公私财物数额较大怎么处罚？", "中华人民共和国刑法", "第二百六十六条", "刑事", "中"),
    ("去法院起诉需要符合什么条件？", "中华人民共和国民事诉讼法", "第一百二十二条", "程序", "中"),
    ("保险公司拖延理赔怎么办？", "中华人民共和国保险法", "第二十三条", "保险", "中"),
    ("保险公司能以未如实告知为由拒赔吗？", "中华人民共和国保险法", "第十六条", "保险", "难"),
    ("有限责任公司的股东想退出公司怎么办？", "中华人民共和国公司法", "第八十九条", "公司", "难"),
    ("我的个人信息被泄露了怎么维权？", "中华人民共和国个人信息保护法", "第六十九条", "个人信息", "中"),
    ("法定继承的遗产分配顺序是什么？", "中华人民共和国民法典继承编", "第一千一百二十七条", "继承", "易"),
    ("遗嘱有哪几种合法形式？", "中华人民共和国民法典继承编", "第一千一百三十四条", "继承", "中"),
    ("被医院误诊造成损害怎么索赔？", "最高人民法院关于审理医疗损害责任纠纷案件适用法律若干问题的解释", "第一条", "医疗", "难"),
    ("人身损害赔偿的项目和标准是什么？", "最高人民法院关于审理人身损害赔偿案件适用法律若干问题的解释", "第六条", "侵权", "中"),
]

CASE_SECTIONS = ("基本案情", "裁判结果")


async def main():
    from tortoise import Tortoise
    from app.models.law import Law
    from app.models.case import Case
    from app.models.eval_dataset import EvalSample

    await Tortoise.init(
        db_url="postgres://legal_user:legal_pass@localhost:5432/legal_db",
        modules={"models": ["app.models.law", "app.models.case", "app.models.eval_dataset"]},
    )

    # id 续接
    ids = await EvalSample.all().values_list("id", flat=True)
    seq = max((int(i.split("_")[1]) for i in ids
               if i.startswith("qa_") and i.split("_")[1].isdigit()), default=0) + 1
    existing_q = {q for q in await EvalSample.all().values_list("question", flat=True)}

    created = 0

    # ── 1. 场景化法条样本 ──
    # 预加载法条 title 索引（title 前缀 → [(id, art_no)]）
    laws = await Law.all().values("id", "title")
    print(f"库内法条 {len(laws)} 条")
    for question, law_prefix, art_no, category, difficulty in SCENE_QA:
        if question in existing_q:
            continue
        match = [l for l in laws
                 if l["title"] == f"{law_prefix} {art_no}"]
        if not match:
            print(f"  [SKIP] 条文未找到: {law_prefix} {art_no} | {question[:25]}")
            continue
        law = await Law.get(id=match[0]["id"])
        await EvalSample.create(
            id=f"qa_{seq}",
            question=question,
            ground_truth=law.content,
            category=category,
            difficulty=difficulty,
            relevant_law_ids=[law.id],
        )
        seq += 1
        created += 1
    print(f"场景化法条样本: +{created}")

    # ── 2. 案例事实型样本 ──
    case_created = 0
    all_cases = await Case.all()
    cases = [c for c in all_cases
             if c.case_tags and "LawRefBook/Laws" in c.case_tags]
    print(f"典型案例 {len(cases)} 篇")
    for case in cases:
        if not case.content:
            continue
        # 拆节
        sections = {}
        current, buf = None, []
        for line in case.content.split("\n"):
            if line.startswith("## "):
                if current:
                    sections[current] = "\n".join(buf).strip()
                current, buf = line[3:].strip(), []
            elif not line.startswith("#"):
                buf.append(line)
        if current:
            sections[current] = "\n".join(buf).strip()
        fact = sections.get("基本案情", "").strip()
        verdict = sections.get("裁判结果", "").strip()
        if len(fact) < 30 or len(verdict) < 15:
            continue
        # question = 案情首段 + 问句后缀（真实用户咨询式问法）
        fact_para = re.split(r"\n", fact)[0][:180]
        question = f"{fact_para}这种情况下应该怎么处理？"
        if question in existing_q:
            continue
        await EvalSample.create(
            id=f"qa_{seq}",
            question=question,
            ground_truth=verdict,
            category=case.case_type or "民事",
            difficulty="难",
            relevant_case_ids=[str(case.id)],
        )
        seq += 1
        case_created += 1
    print(f"案例事实型样本: +{case_created}")

    total = await EvalSample.all().count()
    print(f"\n评测集扩充完成: 本次 +{created + case_created}，总计 {total} 条")
    await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
