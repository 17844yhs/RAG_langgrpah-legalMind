"""向量存储管理"""
from typing import List, Dict, Optional
from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.rag.embeddings import get_embeddings
from app.config import settings

_vector_store = None

async def init_vector_store():
    """异步初始化向量存储"""
    global _vector_store
    embeddings = get_embeddings()
    _vector_store = Chroma(
        persist_directory=settings.VECTOR_STORE_PATH,
        embedding_function=embeddings,
        collection_name="legal_cases"
    )
    return _vector_store

def get_vector_store():
    """获取向量存储实例"""
    global _vector_store
    if _vector_store is None:
        embeddings = get_embeddings()
        _vector_store = Chroma(
            persist_directory=settings.VECTOR_STORE_PATH,
            embedding_function=embeddings,
            collection_name="legal_cases",
        )
    return _vector_store

class VectorStoreManager:
    """向量存储管理器"""
    def __init__(self):
        self.store = get_vector_store()

    async def add_documents(self, documents: List[Document]):
        self.store.add_documents(documents)
    
    async def similarity_search(self, query: str, k: int = 5, filter: Optional[Dict] = None) -> List[Document]:
        return self.store.similarity_search(query,k=k,filter=filter)
    
    async def similarity_search_with_score(self, query: str, k: int = 5, filter: Optional[Dict] = None) -> List[Document]:
        return self.store.similarity_search_with_score(query,k=k,filter=filter)
