"""
重排序器
对检索结果进行重排序
"""
from typing import List,Dict

class Reranker:
    """重排序器"""
    async def rerank(self,query:str,documents:List[Dict],top_k:int=5) -> List[Dict]:
        """
        重排序文档
        Args:
            query: 查询文本
            documents: 待排序文档列表
            top_k: 返回数量
        Returns:
            重排序后的文档列表
        """
        scored_docs = []
        query_terms = set(query.lower().split())

        for doc in documents:
            content = doc.get('content','') # 提取的内容
            title = doc.get('title','') # 提取标题
            score = sum(1 for term in query_terms if term in content or term in title)
            scored_docs.append((score,doc))
        scored_docs.sort(key=lambda x:x[0],reverse=True)
        return [doc for _,doc in scored_docs[:top_k]]