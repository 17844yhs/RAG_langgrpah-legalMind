"""调试：看 retrieve 返回文档的 id 字段到底是什么"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))


async def main():
    from app.agents.retrieval_agent import get_retrieval_agent
    agent = get_retrieval_agent()
    docs = await agent.retrieve(query="公司一直不和我签书面劳动合同，有什么法律后果？", top_k=5, doc_type="law")
    for d in docs:
        print({k: (str(v)[:44]) for k, v in d.items()})


asyncio.run(main())
