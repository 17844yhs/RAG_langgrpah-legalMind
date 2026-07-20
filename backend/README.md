# LegalMind 后端

## 架构概览

后端基于 **FastAPI + LangGraph** 构建，采用多 Agent 协同工作流处理用户请求。

### 请求处理流程

```
用户请求 → 意图识别 → [法律问答 | 案例检索 | 文书生成] → 响应输出
```

1. **意图识别** (`intent_agent.py`)：LLM 分析用户意图，路由到对应处理节点
2. **法律问答**：`qa_agent.py` 结合 RAG 检索结果生成有据可依的法律解答
3. **案例检索**：`retrieval_agent.py` 调用混合检索，返回相关案例列表
4. **文书生成**：`document_agent.py` 根据用户输入生成结构化法律文书

## 环境变量

参考 `app/config.py` 中的 `Settings` 类，支持通过 `.env` 文件配置：

| 变量                | 说明                  | 默认值                                                 |
| ------------------- | --------------------- | ------------------------------------------------------ |
| `DATABASE_URL`    | PostgreSQL 连接字符串 | `postgresql://user:password@localhost:5432/legal_db` |
| `REDIS_URL`       | Redis 连接字符串      | `redis://localhost:6379/0`                           |
| `SECRET_KEY`      | JWT 签名密钥          | `secret-key`                                         |
| `LLM_API_KEY`     | LLM API 密钥          | —                                                     |
| `LLM_MODEL`       | LLM 模型名            | `gpt-4-turbo-preview`                                |
| `EMBEDDING_MODEL` | Embedding 模型        | `BAAI/bge-small-zh`                                  |

完整配置项见 [config.py](app/config.py)。

## LLM 配置

支持多种 LLM 提供商，在 `.env` 中设置：

```ini
LLM_PROVIDER=openai        # 可选: openai, anthropic, deepseek
LLM_API_KEY=sk-xxx
LLM_MODEL=gpt-4-turbo-preview
```

## RAG 检索管线

混合检索 (`retriever.py`)：向量检索（Chroma）+ BM25 关键词检索，结果合并去重。

```bash
# 构建案例向量索引
uv run python scripts/build_index.py
```

## 运行测试

```bash
uv run pytest -v
uv run pytest test/test_rag.py -v   # RAG 相关测试
uv run pytest test/test_llm.py -v   # LLM 相关测试
uv run pytest test/test_wf.py -v    # 工作流测试
```

## 项目结构

```
backend/
├── app/
│   ├── api/             # 路由处理器
│   ├── agents/          # LangGraph Agent 工作流
│   ├── rag/             # RAG 检索管线
│   ├── llm/             # LLM 客户端与提示词
│   ├── models/          # Tortoise ORM 数据模型
│   ├── services/        # 业务逻辑
│   ├── db/              # 数据库连接
│   ├── utils/           # 工具函数
│   ├── config.py        # 配置管理
│   └── main.py          # 应用入口
├── scripts/             # 工具脚本
├── test/                # 测试
├── pyproject.toml       # 依赖配置
└── README.md
```
