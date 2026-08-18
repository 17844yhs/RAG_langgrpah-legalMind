claude


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
  基于 LLM + RAG 技术的智能法律咨询平台 —— 融合 LangGraph 多 Agent 协同工作流、HITL 人机交互、ReAct 检索子图与混合检索技术，提供专业、精准、可控的法律智能服务。
</p>

---

## ✨ 功能特性

### 核心功能

- **💬 智能法律问答** — 基于 LangGraph Agent 工作流，精准识别用户意图，结合 RAG 检索结果生成有据可依的法律解答
- **🔍 案例检索** — 语义向量 + BM25 关键词混合检索 + BGE-Reranker 重排序，快速定位相关法律案例
- **📝 法律文书生成** — 自动生成民事起诉状、答辩状、律师函等专业法律文书
- **🔄 流式对话** — SSE 实时流式输出，对话体验流畅自然
- **📚 多轮对话** — 基于 LangGraph Checkpointer 持久化对话状态，支持上下文延续
- **🔐 用户认证** — JWT 身份认证，保护用户数据安全

### 技术亮点

- **🤝 Human-in-the-Loop 人机交互** — 两个 HITL 检查点：意图确认（置信度 < 0.8 触发澄清）和检索质量评估（结果不足时引导用户补充信息），基于 LangGraph `interrupt` API 实现
- **🛠️ Tool Calling + 参数校验** — `search_cases` Tool 使用 Pydantic Schema 校验（年份范围、案由枚举），LLM 自动提取结构化参数，4 层错误处理架构
- **🧩 ReAct 检索子图** — 自行封装的 4 节点子图（agent → tools → evaluate → finish），支持自动重试（3 轮）和 HITL 介入
- **📊 混合检索管线** — BM25 + 向量检索 + RRF（Reciprocal Rank Fusion）融合 + BGE-Reranker-v2-m3 精排，三级检索管线
- **📐 Structured Output** — `with_structured_output(method="function_calling")` 约束 LLM 输出格式，意图识别返回结构化 `IntentResult`
- **📡 LangSmith 全链路追踪** — 覆盖意图识别 → 检索 → 重排 → 生成全链路，支持按 session_id 回溯
- **📋 RAGAS 评估体系** — 100 条标注数据集 + RAGAS 4 指标评估（faithfulness / answer_relevancy / context_precision / context_recall）+ 自定义 LLM Judge

## 🏗️ 技术栈

| 后端                   | 前端                    | 基础设施          |
| ---------------------- | ----------------------- | ----------------- |
| Python 3.14+           | Vue 3 (Composition API) | PostgreSQL 16     |
| FastAPI                | Vite 8                  | Redis 7           |
| LangChain / LangGraph  | Tailwind CSS 4          | Docker Compose    |
| Tortoise ORM           | Pinia 状态管理          | Chroma 向量数据库 |
| JWT (python-jose)      | Vue Router 5            | LangSmith 追踪    |
| BGE-Reranker-v2-m3     | Axios / marked          | —                |
| LangGraph Checkpointer | —                      | —                |

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

### 6. 运行评估（可选）

```bash
cd backend

# RAGAS 评估
uv run python scripts/evaluate.py --ragas

# 自定义 LLM Judge 评估
uv run python scripts/evaluate.py --judge
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
│   │   │   ├── workflow.py      # StateGraph 主图编排
│   │   │   ├── intent_agent.py  # 意图识别（Structured Output）
│   │   │   ├── retrieval_agent.py # ReAct 检索子图
│   │   │   ├── qa_agent.py      # 法律问答
│   │   │   ├── document_agent.py # 文书生成
│   │   │   └── human_loop.py    # HITL 意图确认节点
│   │   ├── rag/                 # RAG 检索管线
│   │   │   ├── embeddings.py    # BGE 中文 Embedding
│   │   │   ├── vector_store.py  # Chroma 向量存储
│   │   │   ├── retriever.py     # 混合检索 + RRF 融合 + filters 过滤
│   │   │   └── reranker.py      # BGE-Reranker-v2-m3 重排序
│   │   ├── tools/               # LangChain Tool Calling
│   │   │   └── search_tool.py   # search_cases Tool（参数校验 + 4 层错误处理）
│   │   ├── llm/                 # LLM 集成
│   │   │   ├── model_client.py  # LLM 客户端工厂
│   │   │   ├── prompts.py       # 提示词模板
│   │   │   └── checkpoint.py    # 对话状态持久化
│   │   ├── models/              # Tortoise ORM 数据模型
│   │   ├── services/            # 业务逻辑
│   │   ├── db/                  # 数据库连接
│   │   ├── utils/               # 工具函数
│   │   ├── config.py            # Pydantic Settings 配置
│   │   └── main.py              # 应用入口
│   ├── scripts/                 # 工具脚本
│   │   ├── build_index.py       # 构建向量索引
│   │   ├── evaluate.py          # RAGAS + 自定义评估
│   │   ├── supplement_laws.py   # 法条增量补充
│   │   ├── crawl_legal_data.py  # 数据爬取
│   │   ├── clean_data.py        # 数据清洗
│   │   └── import_eval_data.py  # 评估数据导入
│   ├── data/                    # 数据集
│   │   └── legal_eval_dataset_v2.json  # 100 条标注评估集
│   ├── test/                    # 测试
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/                 # API 客户端
│   │   ├── components/          # UI 组件
│   │   │   └── chat/
│   │   │       ├── ChatSidebar.vue    # 聊天侧边栏
│   │   │       ├── ChatMessage.vue    # 消息气泡（Markdown 渲染）
│   │   │       ├── ChatInput.vue      # 消息输入框
│   │   │       └── InterruptCard.vue   # HITL 交互卡片
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
| `/api/chat/resume`                 | POST   | 恢复 HITL 中断的会话     |
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

## 📊 评估指标

| 指标                   | 数值   |
| ---------------------- | ------ |
| RAGAS Context Recall   | 0.90   |
| RAGAS Answer Relevancy | 0.95   |
| 自定义评估 答案相关性  | 0.94   |
| 自定义评估 忠实度      | 0.82   |
| 评估数据集规模         | 100 条 |

## 🗺️ 路线图

- [ ] 多级缓存体系（Embedding 缓存 + 语义缓存）
- [ ] 限流与熔断（Token Bucket + 熔断三态）
- [ ] PostgresSaver 持久化 Checkpoint
- [ ] 异步任务队列（Redis Stream + Worker）
- [ ] astream_events 分阶段进度推送
- [ ] Self-Reflection 质量评估节点
- [ ] OpenTelemetry 全链路追踪
- [ ] CI/CD 自动化测试与部署
- [ ] 支持多模态输入（图片/PDF 证据上传）

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

<p align="center">Made with ❤️ for legal tech innovation</p>
