# LegalMind — Codex 项目指南

## 项目简介

LegalMind 是一个基于 LLM 与 RAG 技术的**智能法律咨询系统**。用户可以进行法律问答、案例检索、法律文书生成。

## 技术栈

- **后端**: Python >=3.14, FastAPI, LangChain, LangGraph, Tortoise ORM
- **AI/LLM**: LangGraph Agent 工作流, OpenAI/DeepSeek/Anthropic LLM, BGE 中文 Embedding
- **RAG**: Chroma 向量数据库, BM25 混合检索, Reranker 重排序
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
│   │   ├── rag/              # RAG 检索管线（vector, BM25, reranker）
│   │   ├── llm/              # LLM 客户端、提示词模板
│   │   ├── models/           # Tortoise ORM 数据模型
│   │   ├── services/         # 业务逻辑层
│   │   ├── db/               # 数据库连接
│   │   ├── utils/            # 工具函数（密码哈希、JWT）
│   │   ├── config.py         # Pydantic Settings 配置
│   │   └── main.py           # FastAPI 入口
│   ├── scripts/              # 工具脚本
│   ├── test/                 # 测试
│   └── pyproject.toml        # 依赖管理
├── frontend/
│   ├── src/
│   │   ├── api/              # Axios API 客户端
│   │   ├── components/       # 通用及业务组件
│   │   ├── views/            # 页面视图
│   │   ├── stores/           # Pinia 状态管理
│   │   └── router/           # Vue Router 路由
│   └── package.json
└── README.md
```

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

## 代码规范

- 采用中文注释，与现有代码风格一致
- API 路由 tags 使用中文（如 `tags=["认证"]`）
- Python 使用 `uv` 管理依赖，配置文件为 `pyproject.toml`
- 前端使用 Vue 3 `<script setup>` 组合式 API

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
```
