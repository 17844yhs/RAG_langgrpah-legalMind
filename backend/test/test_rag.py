import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncio
from app.agents.retrieval_agent import RetrievalAgent

async def test():
    agent = RetrievalAgent()
    results = await agent.retrieve("离婚财产分割", top_k=1)
    for r in results:
        print(r["title"])

asyncio.run(test())
# 应输出：张三与李四离婚财产纠纷案