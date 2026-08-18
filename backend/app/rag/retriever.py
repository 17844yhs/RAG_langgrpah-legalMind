"""混合检索器 — RRF 融合向量检索和 BM25 关键词检索"""
import os
import pickle
import logging
from typing import List, Dict, Optional
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from app.rag.vector_store import get_vector_store
from app.config import settings


logger = logging.getLogger(__name__)


def _rrf_fusion(
    doc_lists: List[List[Document]],
    weights: List[float] = None,
    k: int = 60,
) -> List[Document]:
    """Reciprocal Rank Fusion — 多路检索结果融合排序
    score(d) = Σ weight_i / (k + rank_i(d))
    k 是平滑常数（默认 60），rank 从 1 开始。
    """
    if weights is None:
        weights = [1.0] * len(doc_lists)

    scores: Dict[str, float] = {}
    doc_map: Dict[str, Document] = {}

    for docs, weight in zip(doc_lists, weights):
        for rank, doc in enumerate(docs, start=1):
            doc_id = doc.metadata.get("id", str(id(doc)))
            scores[doc_id] = scores.get(doc_id, 0) + weight / (k + rank)
            doc_map[doc_id] = doc

    # 按 RRF 分数降序排列
    sorted_ids = sorted(scores, key=scores.get, reverse=True)
    # sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_map[did] for did in sorted_ids]


class HybridRetriever:
    """混合检索器 — RRF 融合"""

    def __init__(self):
        self.vector_store = get_vector_store()

        # 向量检索器
        self.vector_retriever = self.vector_store.as_retriever(
            search_kwargs={"k": settings.RAG_TOP_K * 2}
        )

        # BM25 检索器 — 从向量库中加载已有文档来初始化
        self.bm25_retriever = None
        self._init_bm25_from_store()

    def _init_bm25_from_store(self):
        """从持久化文件加载 BM25 索引；失败则从向量库重建并持久化

        持久化策略：
        - 首次启动：从向量库全量加载 → 构建 BM25 → pickle 持久化
        - 后续启动：直接 load pickle，跳过向量库查询和索引构建（快 10-100x）
        - build_index.py 重建向量库时会删除 pickle，强制重新构建
        """
        # 1. 尝试加载持久化索引
        if os.path.exists(settings.BM25_INDEX_PATH):
            try:
                with open(settings.BM25_INDEX_PATH, "rb") as f:
                    self.bm25_retriever = pickle.load(f)
                logger.info(
                    "BM25 索引已从持久化文件加载: %s",
                    settings.BM25_INDEX_PATH,
                )
                return
            except Exception as e:
                logger.warning(
                    "BM25 持久化索引加载失败，回退到重建: %s", e
                )

        # 2. 从向量库重建
        existing = self.vector_store.get()
        if existing and existing.get("documents"):
            docs = [
                Document(page_content=doc, metadata=meta or {})
                for doc, meta in zip(existing.get("documents"), existing.get("metadatas"))
            ]
            self.bm25_retriever = BM25Retriever.from_documents(
                docs, k=settings.RAG_TOP_K * 2
            )
            logger.info(
                "BM25 索引已从向量库重建：%d 个文档", len(docs)
            )

            # 3. 持久化索引（失败不影响运行）
            try:
                os.makedirs(
                    os.path.dirname(settings.BM25_INDEX_PATH) or ".",
                    exist_ok=True,
                )
                with open(settings.BM25_INDEX_PATH, "wb") as f:
                    pickle.dump(self.bm25_retriever, f)
                logger.info("BM25 索引已持久化到 %s", settings.BM25_INDEX_PATH)
            except Exception as e:
                logger.warning("BM25 索引持久化失败（不影响运行）: %s", e)

    @staticmethod
    def _is_simple_filter(filters: Dict) -> bool:
        """判断是否为简单等值过滤（可下推到 Chroma 向量库）"""
        return all(not isinstance(v, dict) for v in filters.values())

    @staticmethod
    def _matches_filter(metadata: Dict, filters: Dict) -> bool:
        """判断文档 metadata 是否满足过滤条件
        支持:
          - 简单等值: {"court": "最高法院"}
          - $contains: {"laws": {"$contains": "合同法"}}  (字符串子串 / 列表元素匹配)
          - $in:      {"category": {"$in": ["劳动争议","合同纠纷"]}}
          - $neq:     {"court": {"$neq": "某法院"}}
        """
        if not filters:
            return True
        for key, condition in filters.items():
            value = metadata.get(key)
            if isinstance(condition, dict):
                for op, expected in condition.items():
                    if op == "$contains":
                        if value is None:
                            return False
                        if isinstance(value, list):
                            if not any(str(expected) in str(item) for item in value):
                                return False
                        elif isinstance(value, str):
                            if str(expected) not in value:
                                return False
                        else:
                            if str(expected) not in str(value):
                                return False
                    elif op == "$in":
                        if value not in expected:
                            return False
                    elif op == "$neq":
                        if value == expected:
                            return False
                    else:
                        return False
            else:
                if value != condition:
                    return False
        return True

    async def retrieve(self, query: str, top_k: int = 10, filters: Optional[Dict] = None) -> List[Dict]:
        """
        混合检索（RRF 融合）
        Args:
            query: 查询文本
            top_k: 返回数量
            filters: 过滤条件
        Returns:
            检索结果列表
        """
        # 向量检索 — 简单等值过滤下推到向量库，复杂过滤走后置兜底
        vector_docs = []
        if filters and self._is_simple_filter(filters):
            try:
                vector_docs = self.vector_store.similarity_search(
                    query, k=settings.RAG_TOP_K * 2, filter=filters
                )
            except Exception:
                vector_docs = await self.vector_retriever.ainvoke(query)
        else:
            vector_docs = await self.vector_retriever.ainvoke(query)

        # BM25 检索
        bm25_docs = []
        if self.bm25_retriever:
            bm25_docs = self.bm25_retriever.invoke(query)

        # RRF 融合排序（BM25 权重 0.4，向量权重 0.6）
        if bm25_docs:
            docs = _rrf_fusion(
                [bm25_docs, vector_docs],
                weights=[0.4, 0.6],
            )
        else:
            docs = vector_docs

        # 后置过滤（兜底：对 BM25 结果和向量结果做统一过滤）
        if filters:
            docs = [doc for doc in docs if self._matches_filter(doc.metadata, filters)]

        return [self._doc_to_dict(doc) for doc in docs[:top_k]]


    # def _merge_results(self, vector_docs, bm25_docs, top_k):
    #     """合并检索结果 — 向量结果优先，BM25 补充遗漏"""
    #     seen_ids = set()
    #     results = []
    #     for doc in vector_docs:
    #         if hasattr(doc, "metadata"):
    #             doc_id = doc.metadata.get("id")
    #             if doc_id and doc_id not in seen_ids:
    #                 results.append(self._doc_to_dict(doc))
    #                 seen_ids.add(doc_id)
    #     for doc in bm25_docs:
    #         if hasattr(doc, 'metadata'):
    #             doc_id = doc.metadata.get('id')
    #             if doc_id and doc_id not in seen_ids:
    #                 results.append(self._doc_to_dict(doc))
    #                 seen_ids.add(doc_id)
    #     return results[:top_k]

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
