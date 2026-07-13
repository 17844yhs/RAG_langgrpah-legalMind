"""意图识别 Agent — 识别用户意图：法律问答、文书生成、案例检索"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.llm.model_client import get_llm
from app.llm.prompts import INTENT_RECOGNITION_PROMPT


class IntentAgent:
    """意图识别 Agent"""
    def __init__(self):
        self.llm = get_llm()
        self.prompt = ChatPromptTemplate.from_template(INTENT_RECOGNITION_PROMPT)
        self.chain = self.prompt | self.llm | StrOutputParser()
    
    async def recognize(self,query:str) ->str:
        response = await self.chain.ainvoke({"query":query})
        intent = response.strip().lower()
        if intent not in ['qa','document','search']:
            intent ='qa'
        return intent