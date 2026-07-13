<p align="center">
  <img src="frontend/src/assets/hero.png" alt="LegalMind" width="400"/>
</p>

<h1 align="center">LegalMind · 智能法律咨询系统</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.14+-blue?logo=python" alt="Python 3.14+"/>
  <img src="https://img.shields.io/badge/FastAPI-0.136+-009688?logo=fastapi" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/Vue_3-3.5-4FC08D?logo=vue.js" alt="Vue 3"/>
  <img src="https://img.shields.io/badge/LangGraph-1.2-FF6F00" alt="LangGraph"/>
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License"/>
</p>

<p align="center">
  基于 LLM + RAG 技术的智能法律咨询平台 —— 融合 LangGraph 多 Agent 协同工作流与混合检索技术，提供专业、精准的法律智能服务。
</p>

---

## ✨ 功能特性

- **💬 智能法律问答** — 基于 LangGraph Agent 工作流，精准识别用户意图，结合 RAG 检索结果生成有据可依的法律解答
- **🔍 案例检索** — 支持语义向量 + BM25 关键词混合检索，快速定位相关法律案例
- **📝 法律文书生成** — 自动生成民事起诉状、答辩状、律师函等专业法律文书
- **🔄 流式对话** — SSE 实时流式输出，对话体验流畅自然
- **📚 多轮对话** — 基于 LangGraph Checkpointer 持久化对话状态，支持上下文延续
- **🔐 用户认证** — JWT 身份认证，保护用户数据安全

## 🏗️ 技术栈

| 后端                   | 前端                    | 基础设施          |
| ---------------------- | ----------------------- | ----------------- |
| Python 3.14+           | Vue 3 (Composition API) | PostgreSQL 16     |
| FastAPI                | Vite 8                  | Redis 7           |
| LangChain / LangGraph  | Tailwind CSS 4          | Docker Compose    |
| Tortoise ORM           | Pinia 状态管理          | Chroma 向量数据库 |
| JWT (python-jose)      | Vue Router 5            | —                |
| LangGraph Checkpointer | Axios / marked          | —                |

## 🚀 快速开始

### 前置条件

- Python >= 3.14（[安装 uv](https://docs.astral.sh/uv/getting-started/installation/)）
- Node.js >= 18 + pnpm
- Docker & Docker Compose（可选，用于启动数据库）

### 1. 克隆项目

```bash
git clone https://github.com/your-username/legal-mind.git
cd legal-mind
```

### 2. 启动基础设施

```bash
docker compose up -d
```

此命令会启动 PostgreSQL 16 和 Redis 7，并创建 `legal_db` 数据库。

### 3. 启动后端

```bash
cd backend

# 创建环境变量文件
# （将 .env.example 复制为 .env 并填写配置）
cp .env.example .env

# 安装依赖
uv sync

# 启动开发服务器
uv run uvicorn app.main:app --port 8000 --reload
```

API 文档：启动后访问 [http://localhost:8000/docs](http://localhost:8000/docs)

### 4. 启动前端

```bash
cd frontend

# 安装依赖
pnpm install

# 启动开发服务器
pnpm dev
```

前端页面：启动后访问 [http://localhost:5173](http://localhost:5173)

### 5. 构建向量索引（可选）

```bash
cd backend
uv run python scripts/build_index.py
```

---

## 📁 项目结构

```
legal_mind/
├── docker-compose.yml           # PostgreSQL + Redis
├── backend/
│   ├── app/
│   │   ├── api/                 # 路由处理器（auth, chat, documents, cases）
│   │   ├── agents/              # LangGraph Agent 工作流
│   │   │   ├── workflow.py      # StateGraph 编排
│   │   │   ├── intent_agent.py  # 意图识别
│   │   │   ├── retrieval_agent.py # 案例检索
│   │   │   ├── qa_agent.py      # 法律问答
│   │   │   └── document_agent.py # 文书生成
│   │   ├── rag/                 # RAG 检索管线
│   │   │   ├── embeddings.py    # Embedding 模型
│   │   │   ├── vector_store.py  # Chroma 向量存储
│   │   │   ├── retriever.py     # 混合检索（向量 + BM25）
│   │   │   └── reranker.py      # 结果重排序
│   │   ├── llm/                 # LLM 集成
│   │   │   ├── model_client.py  # LLM 客户端工厂
│   │   │   ├── prompts.py       # 提示词模板
│   │   │   └── checkpoint.py    # 对话状态持久化
│   │   ├── models/              # 数据模型
│   │   ├── services/            # 业务逻辑
│   │   ├── db/                  # 数据库连接
│   │   ├── utils/               # 工具函数
│   │   ├── config.py            # 配置管理
│   │   └── main.py              # 应用入口
│   ├── scripts/                 # 工具脚本
│   ├── test/                    # 测试
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/                 # API 客户端
│   │   ├── components/          # UI 组件
│   │   ├── views/               # 页面视图
│   │   ├── stores/              # 状态管理
│   │   └── router/              # 路由配置
│   └── package.json
├── .gitignore
├── CLAUDE.md
├── CHANGELOG.md
├── CONTRIBUTING.md
└── README.md
```

## 📡 API 概览

| 路径                                 | 方法   | 说明                     |
| ------------------------------------ | ------ | ------------------------ |
| `/health`                          | GET    | 健康检查                 |
| `/api/auth/register`               | POST   | 用户注册                 |
| `/api/auth/login`                  | POST   | 用户登录（返回 JWT）     |
| `/api/chat/send`                   | POST   | 发送聊天消息（非流式）   |
| `/api/chat/stream`                 | POST   | 发送聊天消息（SSE 流式） |
| `/api/chat/sessions`               | GET    | 获取会话列表             |
| `/api/chat/sessions/{id}/messages` | GET    | 获取会话消息             |
| `/api/chat/sessions/{id}`          | DELETE | 删除会话                 |
| `/api/documents/generate`          | POST   | 生成法律文书             |
| `/api/cases/search`                | GET    | 搜索案例                 |
| `/api/cases/list`                  | GET    | 获取案例列表             |

## 🧪 运行测试

```bash
cd backend
uv run pytest             # 运行全部测试
uv run pytest -v          # 详细输出
uv run pytest test/test_rag.py -v  # 单个测试文件
```

## 🗺️ 路线图

- [ ] 增加更多法律文书模板
- [ ] 支持多模态输入（图片/PDF 证据上传）
- [ ] 接入法律知识图谱
- [ ] 裁判文书数据批量导入
- [ ] 智能法律风险评估
- [ ] CI/CD 自动化测试与部署

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

<p align="center">Made with ❤️ for legal tech innovation</p>
