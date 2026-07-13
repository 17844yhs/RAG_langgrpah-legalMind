from langchain_openai import ChatOpenAI
from app.config import settings

_llm = None
# 非线程安全,单线程应用（FastAPI 单进程）可用;多线程无参函数用functools.lru_cache
def get_llm():
    global _llm
    if _llm is None:
        _llm = _init_llm()
    return _llm

def _init_llm():
    common = {
        "temperature": settings.LLM_TEMPERATURE, 
        "max_tokens": settings.LLM_MAX_TOKENS
        }
    if settings.LLM_PROVIDER =="deepseek":
        return ChatOpenAI(model=settings.LLM_MODEL,openai_api_key=settings.LLM_API_KEY,
                          openai_api_base="https://api.deepseek.com/v1",**common)
    elif settings.LLM_PROVIDER == "openai":
        return ChatOpenAI(model=settings.LLM_MODEL,openai_api_key=settings.LLM_API_KEY,**common)
    
    else:
        raise ValueError(f'不支持这个服务商:{settings.LLM_PROVIDER}')

class LLMClient:
    def __init__(self):
        self.llm= get_llm()

    async def generate(self,prompt:str) ->str:
        resp = await self.llm.ainvoke(prompt)
        return resp.content
    
    async def stream(self,prompt:str):
        async for chunk in self.llm.stream(prompt):
            yield chunk.content