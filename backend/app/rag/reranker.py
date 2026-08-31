"""重排序器 — 基于 CrossEncoder 交叉注意力打分

使用 BAAI/bge-reranker-v2-m3 做 query-document 语义相关性评分，
替代原来的关键词重叠计数。

性能设计（CPU 推理 ~20s → ~2-4s）：
- max_length=256：相关性判断只需看段落开头，bge-reranker-v2-m3 默认
  8192 上下文会让 1000 字 chunk 全长推理，白白慢 3-4 倍
- predict 是同步 CPU 密集调用，扔线程池执行——不阻塞事件循环，
  期间同一进程的其他请求正常服务

注：langchain.retrievers 模块在 LangChain 1.3.9 中已移除，
    改用 sentence_transformers.CrossEncoder 直接调用。
"""
import asyncio
import os
from typing import List, Dict

from sentence_transformers import CrossEncoder

_LOCAL_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models"
)

# rerank 输入截断：查询 + 文档前缀足够做相关性判断
_MAX_DOC_CHARS = 400
_MAX_SEQ_LEN = 256


def _load_reranker_model(model_name: str) -> CrossEncoder:
    """加载 Reranker 模型：本地缓存 → ModelScope → HuggingFace"""
    # 1. 检查 ModelScope 本地缓存
    local_dir = os.path.join(_LOCAL_MODEL_DIR, model_name.replace("/", "--"))
    if os.path.isdir(local_dir):
        return CrossEncoder(local_dir, max_length=_MAX_SEQ_LEN)

    # 2. 从 ModelScope 下载
    try:
        from modelscope import snapshot_download
        print(f"  从 ModelScope 下载 reranker: {model_name} ...")
        snapshot_download(model_name, local_dir=local_dir)
        return CrossEncoder(local_dir, max_length=_MAX_SEQ_LEN)
    except ImportError:
        pass

    # 3. 回退到 HuggingFace（可能需要翻墙）
    return CrossEncoder(model_name, max_length=_MAX_SEQ_LEN)


class Reranker:
    """重排序器 — CrossEncoder 语义重排"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        self._model = _load_reranker_model(model_name)

    async def rerank(self, query: str, documents: List[Dict], top_k: int = 5) -> List[Dict]:
        """
        重排序文档
        Args:
            query: 查询文本
            documents: 待排序文档列表（dict 格式）
            top_k: 返回数量
        Returns:
            重排序后的文档列表（dict 格式，带 rerank_score）
        """
        if not documents:
            return []

        # 构建 [query, document] 对（文档截断前缀，配合 max_length=256 控制推理开销）
        pairs = [
            [query, f"{doc.get('title', '')}\n{doc.get('content', doc.get('summary', ''))}"[:_MAX_DOC_CHARS]]
            for doc in documents
        ]

        # CrossEncoder 打分 — 同步 CPU 密集调用扔线程池，不阻塞事件循环
        scores = await asyncio.to_thread(self._model.predict, pairs)

        # 按分数降序排列
        scored = sorted(
            zip(documents, scores),
            key=lambda x: float(x[1]),
            reverse=True,
        )

        # 去重（同 title 只保留最高分 chunk）+ 取 top_k
        result = []
        seen_titles = set()
        for doc, score in scored:
            title = doc.get("title", "")
            # 跳过重复标题（同一法律/案例的不同 chunk）
            if title and title in seen_titles:
                continue
            if title:
                seen_titles.add(title)
            doc["rerank_score"] = float(score)
            result.append(doc)
            if len(result) >= top_k:
                break

        return result

    # ── 旧版：无去重，直接截取 top_k ──
    # async def rerank_old(self, query, documents, top_k=5):
    #     ...
    #     for doc, score in scored[:top_k]:
    #         doc["rerank_score"] = float(score)
    #         result.append(doc)
    #     return result



# 手写简单的重排序器
# class KeywordReranker:
#     async def rerank(self, query: str, documents: List[Dict], top_k: int = 5) -> List[Dict]:
#         scored_docs = []
#         query_terms = set(query.lower().split())
#         for doc in documents:
#             content = doc.get('content', '')
#             title = doc.get('title', '')
#             score = sum(1 for term in query_terms if term in content or term in title)
#             scored_docs.append((score, doc))
#         scored_docs.sort(key=lambda x: x[0], reverse=True)
#         return [doc for _, doc in scored_docs[:top_k]]