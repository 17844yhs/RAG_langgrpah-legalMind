# LegalMind 后端

## 架构概览

后端基于 **FastAPI + LangGraph** 构建，采用多 Agent 协同工作流处理用户请求。

### 请求处理流程

```
用户请求
  ↓
意图识别（Structured Output → IntentResult）
  ↓
check_intent（HITL：置信度 < 0.8 → interrupt → 用户确认）
  ↓
路由 → [法律问答 | 案例检索 | 文书生成]
  ↓
  ├── 法律问答：RAG 检索 → QA 生成（引用法条 + 案例）
  ├── 案例检索：ReAct 子图（agent → tools → evaluate → finish）
  │     ├── agent：LLM bind_tools，提取检索参数
  │     ├── tools：ToolNode 执行 search_cases（参数校验 + filters 过滤）
  │     ├── evaluate：≥3 条→done，<3 且 retry<3→重试，retry 耗尽→HITL interrupt
  │     └── finish：整理结果返回主图
  └── 文书生成：LLM 生成结构化法律文书
  ↓
响应输出（SSE 流式）
```

### 核心组件

| 组件 | 文件 | 说明 |
|------|------|------|
| 主图编排 | `agents/workflow.py` | StateGraph 主图，3 Agent 路由 + HITL 节点 |
| 意图识别 | `agents/intent_agent.py` | `with_structured_output(IntentResult, method="function_calling")` |
| ReAct 检索子图 | `agents/retrieval_agent.py` | 4 节点子图，支持自动重试 + HITL |
| HITL 节点 | `agents/human_loop.py` | 意图确认 `interrupt` |
| 法律问答 | `agents/qa_agent.py` | 结合 RAG 检索结果生成回答 |
| 文书生成 | `agents/document_agent.py` | 流式生成法律文书 |

### Human-in-the-Loop 机制

两个 HITL 检查点，基于 LangGraph `interrupt` API：

1. **check_intent**（主图）：意图置信度 < 0.8 时触发 interrupt，生成澄清问题等待用户确认
2. **evaluate**（检索子图内）：检索结果 < 3 条且重试耗尽时触发 interrupt，引导用户补充信息

中断后通过 `POST /api/chat/resume` 端点恢复执行。

## 环境变量

参考 `app/config.py` 中的 `Settings` 类，支持通过 `.env` 文件配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql://user:password@localhost:5432/legal_db` |
| `REDIS_URL` | Redis 连接字符串 | `redis://localhost:6379/0` |
| `SECRET_KEY` | JWT 签名密钥 | `secret-key` |
| `LLM_PROVIDER` | LLM 提供商 | `openai`（可选: openai, anthropic, deepseek） |
| `LLM_API_KEY` | LLM API 密钥 | — |
| `LLM_MODEL` | LLM 模型名 | `gpt-4-turbo-preview` |
| `LLM_API_BASE` | LLM API 地址 | 按提供商默认 |
| `EMBEDDING_MODEL` | Embedding 模型 | `BAAI/bge-small-zh` |
| `LANGSMITH_TRACING` | LangSmith 追踪开关 | `false` |
| `LANGSMITH_ENDPOINT` | LangSmith 端点 | `https://api.smith.langchain.com` |
| `LANGSMITH_API_KEY` | LangSmith API Key | — |
| `LANGSMITH_PROJECT` | LangSmith 项目名 | `legalmind` |

完整配置项见 [config.py](app/config.py)。

## LLM 配置

支持多种 LLM 提供商，在 `.env` 中设置：

```ini
LLM_PROVIDER=deepseek         # 可选: openai, anthropic, deepseek
LLM_API_KEY=sk-xxx
LLM_MODEL=deepseek-chat
LLM_API_BASE=https://api.deepseek.com/v1
```

**DeepSeek 兼容性**：DeepSeek 不支持 `json_schema` response format，已改用 `method="function_calling"` 模式。

## RAG 检索管线

三级检索管线（`retriever.py` + `reranker.py`）：

```
用户查询 → 向量检索（Chroma）+ BM25 关键词检索
  ↓
RRF 融合（Reciprocal Rank Fusion，k=60）
  ↓
BGE-Reranker-v2-m3 精排（CrossEncoder）
  ↓
Top-K 结果
```

- **混合检索**：向量检索（语义）+ BM25（关键词），通过 RRF 融合排序
- **filters 过滤**：支持简单等值 / `$contains` / `$in` / `$neq` 四种操作符
- **分块策略**：法律文本 1000 字 chunk（overlap=100），案例文本 500 字（overlap=50）

```bash
# 构建案例向量索引
uv run python scripts/build_index.py
```

## Tool Calling

`search_cases` Tool（`tools/search_tool.py`）：

- **参数提取**：LLM 从自然语言提取 `court`、`year`、`category` 等结构化参数
- **参数校验**：Pydantic Schema + `field_validator`（年份范围、案由枚举）
- **4 层错误处理**：Pydantic 校验 → tenacity 重试 → try-except 兜底 → ToolNode `handle_tool_errors`

## 评估体系

```bash
# RAGAS 评估（4 指标：faithfulness / answer_relevancy / context_precision / context_recall）
uv run python scripts/evaluate.py --ragas

# 自定义 LLM Judge（4 维度：忠实度 / 答案相关性 / 答案正确性 / 上下文相关性）
uv run python scripts/evaluate.py --judge
```

评估数据集：`data/legal_eval_dataset_v2.json`（100 条标注样本，覆盖劳动争议、合同纠纷、婚姻家庭、知识产权、刑事等）

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
│   ├── api/              # 路由处理器（auth, chat, documents, cases）
│   ├── agents/           # LangGraph Agent 工作流
│   │   ├── workflow.py       # StateGraph 主图编排
│   │   ├── intent_agent.py   # 意图识别（Structured Output）
│   │   ├── retrieval_agent.py # ReAct 检索子图
│   │   ├── qa_agent.py       # 法律问答
│   │   ├── document_agent.py # 文书生成
│   │   └── human_loop.py     # HITL 意图确认节点
│   ├── rag/              # RAG 检索管线
│   │   ├── embeddings.py     # BGE 中文 Embedding
│   │   ├── vector_store.py   # Chroma 向量存储
│   │   ├── retriever.py      # 混合检索 + RRF 融合 + filters
│   │   └── reranker.py       # BGE-Reranker-v2-m3
│   ├── tools/            # LangChain Tool Calling
│   │   └── search_tool.py    # search_cases Tool
│   ├── llm/              # LLM 客户端与提示词
│   ├── models/           # Tortoise ORM 数据模型
│   ├── services/         # 业务逻辑层
│   ├── db/               # 数据库连接
│   ├── utils/            # 工具函数
│   ├── config.py         # Pydantic Settings 配置
│   └── main.py           # 应用入口
├── scripts/              # 工具脚本
│   ├── build_index.py        # 构建向量索引
│   ├── evaluate.py           # RAGAS + 自定义评估
│   ├── supplement_laws.py    # 法条增量补充
│   ├── crawl_legal_data.py   # 数据爬取
│   ├── clean_data.py         # 数据清洗
│   └── import_eval_data.py   # 评估数据导入
├── data/                 # 数据集
├── test/                 # 测试
├── pyproject.toml        # 依赖配置
└── README.md
```
