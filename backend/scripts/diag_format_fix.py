"""验证 _format_cases 字段错位修复：法条 chunk 应注入条文原文。用完可删。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.qa_agent import QAAgent

fake = [
    {
        "type": "law",
        "id": "law_107",
        "title": "民法典总则编 第八条",
        "content": "民事主体从事民事活动，不得违反法律，不得违背公序良俗。",
        "case_number": None, "court": None, "summary": None, "laws": None,
    },
    {
        "type": "case",
        "id": "case_01",
        "title": "张三与李四离婚财产纠纷案",
        "case_number": "（2023）京0105民初12345号",
        "court": "北京市朝阳区人民法院",
        "summary": "婚后共同财产股权分割按婚姻家庭编解释处理。",
        "laws": ["《民法典》第一千零八十七条"],
        "content": "全文略（案例全文不进 prompt，只进 rerank）",
    },
]

agent = QAAgent()
print(agent._format_cases(fake))
print("---")
print(agent._format_cases([]))
