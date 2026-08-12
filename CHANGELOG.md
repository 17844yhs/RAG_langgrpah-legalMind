# 更新日志

本文件记录 LegalMind 项目的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.2.0] - 2026-08-12

### 新增

- **🤝 Human-in-the-Loop 人机交互**：两个 HITL 检查点（意图确认 + 检索质量评估），基于 LangGraph `interrupt` API；前端新增 `InterruptCard.vue` 交互卡片；新增 `POST /api/chat/resume` 端点恢复中断会话
- **🛠️ Tool Calling + 参数校验**：`search_cases` Tool（Pydantic Schema + `field_validator` + 4 层错误处理），集成到 ReAct 检索子图
- **🧩 ReAct 检索子图**：4 节点子图（agent → tools → evaluate → finish），支持自动重试（3 轮）和 HITL 介入，替代原 `case_retrieval` + `check_retrieval` 两节点
- **📊 混合检索管线升级**：BM25 + 向量检索 + RRF（Reciprocal Rank Fusion，k=60）融合 + BGE-Reranker-v2-m3 精排
- **📐 Structured Output**：意图识别改用 `with_structured_output(IntentResult, method="function_calling")`，返回结构化意图 + 置信度 + 推理
- **📡 LangSmith 全链路追踪**：覆盖意图→检索→重排→生成全链路，配置统一为 `LANGSMITH_*` 前缀
- **📋 RAGAS 评估体系**：100 条标注数据集 + RAGAS 4 指标 + 自定义 LLM Judge（4 维度评估）
- **⚖️ 法条增量补充**：`supplement_laws.py` 增量补充 17+ 条文，`check` 字段防重复
- **🔄 filters 过滤**：`retrieve()` 支持简单等值 / `$contains` / `$in` / `$neq` 四种过滤操作符

### 修复

- **workflow.py 键名修复**：`message` → `messages`，修复 HumanMessage 丢失
- **model_client.py**：读取 `LLM_API_BASE` 配置，不再硬编码 DeepSeek API 地址
- **DeepSeek Structured Output 兼容**：改用 `method="function_calling"` 解决 400 错误
- **前端流式输出自动滚动**：同时监听消息条数 + 最后一条消息 content 长度
- **Windows 事件循环修复**：uvicorn 0.49.0 + psycopg async 兼容
- **条件边优化**：使用内置 `tools_condition` 替代手写路由函数，清理死代码

### 变更

- **分块策略优化**：法律文本 1000 字 chunk（overlap=100），案例文本 500 字（overlap=50）；法条 keywords 拼入 page_content 提升 BM25 命中率
- **ChromaDB 自动清空**：`build_index.py` 写入前自动清空旧索引
- **前端状态管理**：`chat.js` 新增 `pendingInterrupt` 状态和 `resumeInterrupt()` 方法

---

## [0.1.0] - 2026-07-10

### 新增

- ✨ **智能法律问答**：基于 LangGraph Agent 工作流的法律咨询对话，支持流式 SSE 输出
- 🔍 **案例检索**：通过 RAG（检索增强生成）技术检索相关法律案例，支持向量 + BM25 混合检索
- 📝 **法律文书生成**：支持生成民事起诉状、答辩状、律师函等法律文书
- 💬 **会话管理**：多轮对话历史持久化，基于 LangGraph Checkpointer（PostgreSQL）
- 🔐 **用户认证**：JWT 注册/登录认证系统
- 🎨 **前端界面**：基于 Vue 3 + Tailwind CSS 的现代化 Web 界面
- 🐳 **Docker 支持**：Docker Compose 一键启动 PostgreSQL + Redis 基础设施
