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
        local_path = os.path.join(_LOCAL_MODEL_DIR, model_name.split("/")[-1])
        if os.path.isdir(local_path):
            model_name = local_path  # 本地有就用本地的
            _embeddings = HuggingFaceEmbeddings(
                model_name= model_name,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},  # L2归一化
            )
    return _embeddings