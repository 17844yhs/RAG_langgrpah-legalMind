import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.agents.workflow import workflow

async def test():
    rs = await workflow.run("劳动合同")
    print(rs['response'])

asyncio.run(test())