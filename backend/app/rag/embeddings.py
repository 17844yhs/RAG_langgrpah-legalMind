import os
from langchain_huggingface import HuggingFaceEmbeddings
from app.config import settings

_LOCAL_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models"
)

_embeddings = None

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
        _embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            cache_folder=_LOCAL_MODEL_DIR,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings