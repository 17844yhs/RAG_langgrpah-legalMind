"""向量存储管理 — Chroma 懒加载单例"""
from langchain_chroma import Chroma

from app.rag.embeddings import get_embeddings
from app.config import settings

_vector_store: Chroma | None = None


def _build_store() -> Chroma:
    return Chroma(
        persist_directory=settings.VECTOR_STORE_PATH,
        embedding_function=get_embeddings(),
        collection_name="legal_cases",
    )


def get_vector_store() -> Chroma:
    """获取向量存储单例（懒加载）。init_vector_store 与本函数共用同一构造，避免双份维护。"""
    global _vector_store
    if _vector_store is None:
        _vector_store = _build_store()
    return _vector_store


async def init_vector_store() -> Chroma:
    """lifespan 启动钩子调用：预热构造（嵌入模型加载是重开销，别留给首个请求）。"""
    return get_vector_store()
