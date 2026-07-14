"""
混合检索器
结合向量检索和关键词检索
"""
from typing import List, Dict, Optional
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from app.rag.vector_store import get_vector_store
from app.config import settings

class HybridRetriever:
    """混合检索器"""
    def __init__(self):
        self.vector_store = get_vector_store()

        # 向量检索器
        self.vector_retriever = self.vector_store.as_retriever(
            search_kwargs={"k": settings.RAG_TOP_K * 2}
        )
        self.bm25_retriever = None 
        # BM25 检索器 — 从向量库中加载已有文档来初始化
        self._init_bm25_from_store()
    
    def _init_bm25_from_store(self):
        """从向量库加载已有文档，初始化 BM25 检索器"""
        existing = self.vector_store.get()  # 获取所有已存储的文档
        if existing and existing.get("documents"):
            docs =[
                Document(page_content=doc,metadata=meta or {}) for doc,meta in zip(existing.get("documents"),existing.get("metadatas"))
            ]
            self.bm25_retriever = BM25Retriever.from_documents(docs)
    async def retrieve(self,query: str,top_k: int = 10,filters: Optional[Dict] = None) -> List[Dict]:
        """
        混合检索
        Args:
            query: 查询文本
            top_k: 返回数量
            filters: 过滤条件
        Returns:
            检索结果列表
        """
        # 向量检索
        vector_docs = await self.vector_retriever.ainvoke(
            query,
            config={"filters": filters}
        )

        # BM25 检索
        bm25_docs = []
        if self.bm25_retriever:
            bm25_docs = self.bm25_retriever.invoke(query)

        # 合并去重
        merged = self._merge_results(vector_docs, bm25_docs, top_k)
        return merged
    
    def _merge_results(self,vector_docs:List,bm25_docs:List,top_k:int) ->List[Dict]:
        """合并检索结果 — 向量结果优先，BM25 补充遗漏"""
        seen_ids = set()
        results = []

        # 向量检索结果优先（语义更相关）
        for doc in vector_docs:
            if hasattr(doc,"metadata"):
                doc_id = doc.metadata.get("id")
                if doc_id and doc_id not in seen_ids:
                    results.append(self._doc_to_dict(doc))
                    seen_ids.add(doc_id)
        
        # 补充 BM25 结果（关键词匹配可能捞回向量检索遗漏的）
        for doc in bm25_docs:
            if hasattr(doc, 'metadata'):
                doc_id = doc.metadata.get('id')
                if doc_id and doc_id not in seen_ids:
                    results.append(self._doc_to_dict(doc))
                    seen_ids.add(doc_id)
        
        return results[:top_k]

    def _doc_to_dict(self, doc) -> Dict:
        """文档转字典"""
        return {
            "id": doc.metadata.get("id"),
            "title": doc.metadata.get("title"),
            "content": doc.page_content,
            "case_number": doc.metadata.get("case_number"),
            "court": doc.metadata.get("court"),
            "judgment_date": doc.metadata.get("judgment_date"),
            "summary": doc.metadata.get("summary"),
            "laws": doc.metadata.get("laws"),
            "score": doc.metadata.get("score", 0),
        }
