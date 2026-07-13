"""
案例检索 Agent
基于向量相似度检索相关案例
"""
from typing import List, Dict

from app.rag.retriever import HybridRetriever
from app.rag.reranker import Reranker
from app.config import settings


class RetrievalAgent:
    """案例检索 Agent"""
    def __init__(self):
        self.retriever = HybridRetriever()
        self.reranker = Reranker() if settings.RERANK_ENABLED else None
    
    async def retrieve(self,query: str,top_k: int = 5,filters: Dict = None) -> List[Dict]:
        """
        检索相关案例
        Args:
            query: 查询文本
            top_k: 返回数量
            filters: 过滤条件

        Returns:
            检索到的案例列表
        """
        # 初始检索（多路召回）
        candidates = await self.retriever.retrieve(
            query=query,
            top_k=top_k * 3,
            filters=filters
        )
        # 重排序
        if self.reranker and candidates:
            ranked_results = await self.reranker.rerank(
                            query=query,
                            documents=candidates,
                            top_k=top_k
                        )
            return ranked_results
        return candidates[:top_k]
    

    async def search_by_keywords(
        self,
        keywords: List[str],
        top_k: int = 10
    ) -> List[Dict]:
        """关键词检索"""
        query = " ".join(keywords)
        return await self.retrieve(query, top_k)

    async def search_by_article(
        self,
        article: str,
        top_k: int = 10
    ) -> List[Dict]:
        """按法条检索"""
        filters = {"laws": {"$contains": article}}
        return await self.retrieve(article, top_k, filters)
