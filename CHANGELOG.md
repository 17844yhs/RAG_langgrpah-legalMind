# 更新日志

本文件记录 LegalMind 项目的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.3.0] - 2026-08-27

### 新增

- **🛡️ LLM Fallback 容灾链（with_fallbacks）**：主/备 DeepSeek 双实例容灾，6 类网络/限流异常显式配全；对 `bind_tools` / `with_structured_output` 透明；流式 astream 在首个 chunk 前失败自动切换。规则兜底由应用层降级体系承担（intent 降级 HITL / SSE error 事件）
- **⚡ 混合检索并行化（asyncio.gather）**：BM25（扔线程池）与向量检索并行执行，延迟 sum→max（实测单次检索 ~15ms）；Chroma 过滤下推改用 `asimilarity_search`，同步调用不再阻塞事件循环
- **🔥 修复检索链路 3 个既有性能 bug**（API 层验证时暴露）：① `RetrievalAgent()` 在 5 处调用点请求级实例化 → 每次重新加载 568M cross-encoder 模型，新增 `get_retrieval_agent()` 进程级单例；② `CrossEncoder.predict()` 同步阻塞事件循环 → 扔 `asyncio.to_thread`；③ rerank 全长推理（默认 8192 上下文）→ `max_length=256` + 前缀截断。`GET /api/cases/search` 稳态延迟 20s+ → 9.3s
- **🚨 统一异常处理 + 错误码（RFC 9457 Problem Details）**：新增 `backend/app/exceptions/` 包，错误码注册表（`SYS_/AUTH_/CHAT_/CASE_/RAG_` 前缀）+ 业务异常基类（`AppException` 及领域子类）+ 全局异常处理器，所有错误响应统一为 `application/problem+json` 格式（`type/title/status/detail/instance` 标准字段 + `code/traceId` 扩展字段）
- **🔍 TraceId 全链路排查**：纯 ASGI 中间件为每个请求生成/透传 traceId（请求日志 + 响应头 `X-Request-ID` + 错误体三处携带），未捕获异常堆栈只进日志、对外只回 traceId
- **📡 SSE 错误通道**：流式端点（chat/stream、chat/resume、documents/generate/stream）错误以约定 `error` 事件传递（code + detail + traceId）
- **📐 Structured Output 元数据抽取（LegalAnswerMeta）**：QA 主链路落地"流式 + 结构化"混合方案——正文保持逐 token 流式（打字机效果），流结束后一次轻量结构化调用抽取结论/风险等级/引用法条，经 `meta` SSE 事件送达前端渲染答案卡片（风险配色 + 法条标签 + 一句话结论）。规避 `with_structured_output` 与流式输出的本质互斥（JSON 完整性 vs token 流）
- **💾 元数据持久化**：`chat_messages` 表新增 `meta JSONB` 列，回答元数据随消息一起落库，`GET /sessions/{id}/messages` 带出——刷新页面/加载历史会话时答案卡片不再丢失
- **🗄️ 数据库迁移体系**：启用 tortoise-orm ≥ 1.0 内置迁移 CLI（官方对 1.0+ 的推荐路径，替代 Aerich）。`database.py` 重构为标准 `TORTOISE_ORM` config dict（运行时与 CLI 单一配置来源）；存量库以 `migrate --fake` 登记基线 `0001_initial_baseline`（含 meta 列）；新增 `0002_add_message_list_index` 迁移（`chat_messages(chat_session_id, created_at)` 复合索引，优化历史消息查询）并走真实流程执行验证
- **🛡️ 结构化输出生产加固**：意图识别/信息充分性判断两处补齐容错——`.with_retry` 瞬时失败重试；意图识别失败降级为低置信度 qa 自动触发 HITL 澄清（失败走进人机协作而非报错）；防御 function_calling 模式拒答返回 `None` 的坑

### 修复

- **SSE 流信息泄漏**：原来把原始异常字符串 `{e}` 直接吐给用户（可能含 DB 连接串、模型路径），改为固定文案 + traceId
- **错误响应格式不一致**：裸 `HTTPException`（`{detail}`）、FastAPI 默认 422、框架 404 三种结构并存，前端无法统一处理
- **检索子图路由 KeyError**：`tools_condition` 映射键 `"end"` 应为 `"__end__"`，LLM 不调工具直接回答时崩溃 500（正常流程从不触发，多轮 interrupt/resume 后才暴露）

### 变更

- **参数校验错误状态码 422 → 400**：`SYS_002` 错误码 + `errors` 数组（field/message/type），422 语义留给业务规则校验
- **前端错误处理**：`client.js` 响应拦截器解析 problem 体（`app_code/app_message/trace_id`）；`chat.js`/`documents.js` 流式错误展示后端统一文案
- **API 错误响应结构变更**：`{"detail": "..."}` → `{"type", "title", "status", "detail", "instance", "code", "traceId"}`

---

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
