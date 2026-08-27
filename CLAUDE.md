# LegalMind — Claude Code 项目指南

## 项目简介

LegalMind 是一个基于 LLM 与 RAG 技术的**智能法律咨询系统**。用户可以进行法律问答、案例检索、法律文书生成。系统融合 LangGraph 多 Agent 工作流、HITL 人机交互、ReAct 检索子图与混合检索技术。

## 技术栈

- **后端**: Python >=3.14, FastAPI, LangChain, LangGraph, Tortoise ORM
- **AI/LLM**: LangGraph Agent 工作流, OpenAI/DeepSeek/Anthropic LLM, BGE 中文 Embedding
- **RAG**: Chroma 向量数据库, BM25 混合检索, RRF 融合, BGE-Reranker-v2-m3 重排序
- **工具**: LangChain Tool Calling（search_cases）, Pydantic 参数校验
- **评估**: RAGAS 4 指标 + 自定义 LLM Judge
- **可观测**: LangSmith 全链路追踪
- **数据库**: PostgreSQL 16, Redis 7
- **前端**: Vue 3 (Composition API), Vite 8, Tailwind CSS 4, Pinia, Vue Router
- **容器**: Docker Compose (PostgreSQL + Redis)

## 目录结构

```
legal_mind/
├── docker-compose.yml        # PostgreSQL + Redis
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI 路由（auth, chat, documents, cases）
│   │   ├── agents/           # LangGraph Agent 工作流
│   │   │   ├── workflow.py       # StateGraph 主图编排
│   │   │   ├── intent_agent.py   # 意图识别（Structured Output）
│   │   │   ├── retrieval_agent.py # ReAct 检索子图（4 节点 + HITL）
│   │   │   ├── qa_agent.py       # 法律问答
│   │   │   ├── document_agent.py # 文书生成
│   │   │   └── human_loop.py     # HITL 意图确认节点
│   │   ├── rag/              # RAG 检索管线
│   │   │   ├── embeddings.py     # BGE 中文 Embedding
│   │   │   ├── vector_store.py   # Chroma 向量存储
│   │   │   ├── retriever.py      # 混合检索 + RRF 融合 + filters
│   │   │   └── reranker.py       # BGE-Reranker-v2-m3
│   │   ├── tools/           # LangChain Tool Calling
│   │   │   └── search_tool.py    # search_cases Tool
│   │   ├── llm/              # LLM 客户端、提示词模板
│   │   ├── models/           # Tortoise ORM 数据模型
│   │   ├── services/         # 业务逻辑层
│   │   ├── exceptions/       # 统一异常处理（RFC 9457 错误码 + 全局处理器 + traceId 中间件）
│   │   ├── db/               # 数据库连接
│   │   ├── utils/            # 工具函数（密码哈希、JWT）
│   │   ├── config.py         # Pydantic Settings 配置
│   │   └── main.py           # FastAPI 入口
│   ├── scripts/              # 工具脚本
│   │   ├── build_index.py       # 构建向量索引
│   │   ├── evaluate.py          # RAGAS + 自定义评估
│   │   ├── supplement_laws.py   # 法条增量补充
│   │   ├── crawl_legal_data.py  # 数据爬取
│   │   ├── clean_data.py        # 数据清洗
│   │   └── import_eval_data.py   # 评估数据导入
│   ├── data/                 # 数据集
│   ├── test/                 # 测试
│   └── pyproject.toml        # 依赖管理
├── frontend/
│   ├── src/
│   │   ├── api/              # Axios API 客户端
│   │   ├── components/       # 通用及业务组件
│   │   │   └── chat/
│   │   │       ├── ChatSidebar.vue
│   │   │       ├── ChatMessage.vue
│   │   │       ├── ChatInput.vue
│   │   │       └── InterruptCard.vue  # HITL 交互卡片
│   │   ├── views/            # 页面视图
│   │   ├── stores/          # Pinia 状态管理
│   │   └── router/          # Vue Router 路由
│   └── package.json
└── README.md
```

## 核心架构

### Agent 工作流

```
START → intent_recognition → check_intent(HITL) → router
  ├── qa: retrieval_subgraph → qa_generation → final_output
  ├── search: retrieval_subgraph → final_output
  └── document: document_generation → final_output
→ END
```

### ReAct 检索子图

```
START → agent → (有 tool_calls → tools → evaluate → retry|done) | (无 → finish) → END
```

- evaluate 节点：≥3 条→done，<3 且 retry<3→自动重试，retry 耗尽→HITL interrupt

## 启动方式

```bash
# 启动基础设施（PostgreSQL + Redis）
docker compose up -d

# 后端（在 backend/ 目录下）
cd backend
uv run uvicorn app.main:app --port 8000 --reload

# 前端（在 frontend/ 目录下）
cd frontend
pnpm dev
```

## 文档管理规则（必须遵守）

详见 `.claude/project_rules.md`（工作区根目录）。核心：项目有两份核心文档，用途严格区分：

- **`UPGRADE_PLAN.md`**（改造计划）：待做功能规划 + 概念讲解 + 参考资料；完成的功能项标记 ✅ 并保留原文
- **`优化项目.md`**（执行日志）：已完成功能/Bug 修复（附文件引用与根因）+【待做】条目，极简风格

完成一个功能或修复 Bug 时，两份文档都要按 `project_rules.md` 中的同步规则表更新；同时检查 README.md、CHANGELOG.md 等文档是否需要同步。

## 代码规范

- 采用中文注释，与现有代码风格一致
- API 路由 tags 使用中文（如 `tags=["认证"]`）
- Python 使用 `uv` 管理依赖，配置文件为 `pyproject.toml`
- 前端使用 Vue 3 `<script setup>` 组合式 API
- 提交规范遵循 Conventional Commits（见 CONTRIBUTING.md）

### LangGraph/LangChain 代码规范

- async 函数中禁止同步阻塞调用，CPU 密集型操作用 `asyncio.to_thread` 包装
- 循环节点必须有退出条件（如 `MAX_ROUNDS` 常量），防止无限循环
- interrupt 数据结构必须兼容前端 `InterruptCard.vue` 的 `{"type": ..., "question": ...}` 格式
- 子图状态用 `TypedDict` 定义，内部字段不暴露给主图
- 条件边路径函数返回值应为节点名本身，避免冗余 path_map 映射

## 常用命令

```bash
# 运行后端测试
cd backend && uv run pytest

# 运行单个测试文件
cd backend && uv run pytest test/test_rag.py -v

# 前端 lint
cd frontend && pnpm lint

# 构建向量索引
cd backend && uv run python scripts/build_index.py

# RAGAS 评估
cd backend && uv run python scripts/evaluate.py --ragas

# 自定义 LLM Judge 评估
cd backend && uv run python scripts/evaluate.py --judge

# 法条增量补充
cd backend && uv run python scripts/supplement_laws.py
```
