"""应用配置管理"""
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "LegalMind"
    DEBUG: bool = False
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # 认证配置
    SECRET_KEY: str = "secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # 数据库配置（后续章节会添加更多配置项）
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/legal_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM 配置
    LLM_PROVIDER: str = "openai"  # openai, anthropic, deepseek
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4-turbo-preview"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 4096
    LLM_API_BASE :str = ""
    # 背压控制（见 app/llm/model_client.py）：进程级并发 LLM 调用上限，
    # 超出后在信号量上排队等待而非全部涌入 API（防限流雪崩）
    LLM_MAX_CONCURRENCY: int = 16

    # Embedding 配置
    EMBEDDING_PROVIDER: str = "huggingface"  # openai, huggingface
    EMBEDDING_MODEL: str = "BAAI/bge-small-zh"
    EMBEDDING_DIMENSION: int = 512

    # 向量数据库配置
    VECTOR_STORE: str = "chroma"  # chroma, milvus
    VECTOR_STORE_PATH: str = "./data/chroma"
    BM25_INDEX_PATH: str = "./data/bm25_index.pkl"  # BM25 索引持久化路径
    
    # RAG配置
    RAG_TOP_K: int = 5
    RAG_SCORE_THRESHOLD: float = 0.7
    RERANK_ENABLED: bool = True

    # Context 管理（对话历史视图裁剪 + 自动摘要压缩，见 app/llm/context_manager.py）
    HISTORY_CHAR_BUDGET: int = 6000    # 历史视图预算（字符，≈3-4k token，超了才裁）
    SUMMARY_TRIGGER_CHARS: int = 2000  # 落入裁剪区的未摘要内容超过此字符数才触发摘要 LLM
    SUMMARY_MAX_CHARS: int = 400       # 摘要长度上限（提示词约束，控制摘要自身的 token 开销）

    # Self-Reflection 质量门控（生成-评估-修正循环，见 workflow.quality_gate 节点）
    REFLECTION_ENABLED: bool = True    # 总开关（关闭则 qa_generation 直通 final_output）
    REFLECTION_MAX_ROUNDS: int = 1     # 重试轮数上限（1 = 最多重新生成一次，防止无限循环）
    REFLECTION_SCORE_THRESHOLD: float = 0.6  # 质量分数线（低于则视为不通过）

    # Redis 缓存（见 app/cache/redis_cache.py）：意图识别缓存 + 检索结果缓存
    # 缓存是加速器不是依赖：False 或 Redis 不可达时自动降级直连，业务零感知
    CACHE_ENABLED: bool = True
    INTENT_CACHE_TTL: int = 86400      # 意图缓存 24h（同问题的意图分类基本确定）
    RETRIEVAL_CACHE_TTL: int = 600     # 检索缓存 10min（知识库静态，短窗内同查询复用重排结果）

    # LangSmith 配置
    LANGSMITH_TRACING: bool = True
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "legal"
    class Config:
        env_file = ".env"
        case_sensitive = True # 区分大小写
        extra = "ignore"  # 允许 .env 中有未定义的变量，后续章节会逐步添加


settings = Settings()