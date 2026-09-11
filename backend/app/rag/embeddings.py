import os
import threading
from collections import OrderedDict
from langchain_huggingface import HuggingFaceEmbeddings
from app.config import settings

_LOCAL_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models"
)

_embeddings = None

# ── L1 进程内查询向量缓存（多级缓存体系 L1，L2 为 Redis 检索缓存）────────
# 只缓存 embed_query（每次检索的热路径）；embed_documents 是索引构建批处理，不缓存
_EMBED_CACHE_MAX = 512                     # bge-small 512 维 × 512 条 ≈ 8MB 内存上限
_query_cache: "OrderedDict[str, list[float]]" = OrderedDict()
_cache_lock = threading.Lock()             # embed 经 to_thread 在线程池执行，须加锁


class _QueryCacheMixin:
    """embed_query 的 LRU 缓存混入。

    通用概念：多级缓存 L1/L2/L3——进程内 LRU（L1，纳秒级）→ Redis（L2，毫秒级）
    → 原始计算（L3）。与 CPU 缓存/CDN/buffer pool 同构。
    键归一化与 redis_cache.make_key 保持一致（小写+空白折叠）。
    仅缓存查询向量化：检索结果缓存（L2）命中时根本不会走到这里，本层兜底
    "同 query 不同检索参数（top_k/doc_type）"与"Redis 降级"两种场景。
    """

    def embed_query(self, text: str) -> list[float]:
        key = " ".join(text.split()).lower()
        with _cache_lock:
            hit = _query_cache.get(key)
            if hit is not None:
                _query_cache.move_to_end(key)
                return hit
        vec = super().embed_query(text)    # MRO 指向真实 embedder
        with _cache_lock:
            _query_cache[key] = vec
            while len(_query_cache) > _EMBED_CACHE_MAX:
                _query_cache.popitem(last=False)   # 淘汰最久未用
        return vec


class CachedHuggingFaceEmbeddings(_QueryCacheMixin, HuggingFaceEmbeddings):
    """带 L1 查询缓存的本地嵌入模型"""

def _try_modelscope_download(model_name: str) -> str:
    """HuggingFace 本地缓存不存在时，尝试从 ModelScope 下载"""
    try:
        from modelscope import snapshot_download
        local_dir = os.path.join(_LOCAL_MODEL_DIR, model_name.replace("/", "--"))
        if not os.path.isdir(local_dir):
            print(f"  HuggingFace 缓存未找到，从 ModelScope 下载 {model_name} ...")
            snapshot_download(model_name, local_dir=local_dir)
        return local_dir
    except ImportError:
        print("  提示：可安装 modelscope 以支持国内镜像下载 (uv add modelscope)")
        return model_name

def get_embeddings():
    # 只读取不赋值可以不加 global，否则Python 会认为 _embeddings 是局部变量
    global _embeddings
    if _embeddings is None:
        model_name = settings.EMBEDDING_MODEL
        # 优先查 HuggingFace 本地缓存
        hf_cache_path = os.path.join(_LOCAL_MODEL_DIR, f"models--{model_name.replace('/', '--')}")
        if os.path.isdir(hf_cache_path):
            snapshots_dir = os.path.join(hf_cache_path, "snapshots")
            if os.path.isdir(snapshots_dir):
                hashes = [d for d in os.listdir(snapshots_dir) if os.path.isdir(os.path.join(snapshots_dir, d))]
                if hashes:
                    model_name = os.path.join(snapshots_dir, hashes[0])
        else:
            #  本地无缓存，走 ModelScope 下载 
            model_name = _try_modelscope_download(model_name)
        _embeddings = CachedHuggingFaceEmbeddings(
            model_name=model_name,
            cache_folder=_LOCAL_MODEL_DIR,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings