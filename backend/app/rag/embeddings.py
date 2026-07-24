import os
from langchain_huggingface import HuggingFaceEmbeddings
from app.config import settings

_LOCAL_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models"
)

_embeddings = None

def get_embeddings():
    global _embeddings
    if _embeddings is None:
        model_name = settings.EMBEDDING_MODEL
        hf_cache_path = os.path.join(_LOCAL_MODEL_DIR, f"models--{model_name.replace('/', '--')}")
        if os.path.isdir(hf_cache_path):
            snapshots_dir = os.path.join(hf_cache_path, "snapshots")
            if os.path.isdir(snapshots_dir):
                hashes = [d for d in os.listdir(snapshots_dir) if os.path.isdir(os.path.join(snapshots_dir, d))]
                if hashes:
                    model_name = os.path.join(snapshots_dir, hashes[0])
        _embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            cache_folder=_LOCAL_MODEL_DIR,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings