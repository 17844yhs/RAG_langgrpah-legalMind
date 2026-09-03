# 更新日志

本文件记录 LegalMind 项目的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 新增

- **🚦 k6 性能压测（双模式）**：`loadtest/chat_stream.js`——`infra` 基础设施基线（458 req/s、p95 2.24ms、100 VU 8.2 万请求零错误）+ `chat` 真实 SSE 流式链路（206 条流 0 失败，首事件 p90 57.6ms，整流 p90 13.8s，单条均耗 1,758 tokens）。实测瓶颈在 DeepSeek 上游生成而非应用栈，为路线图"多级缓存 + 限流排队"提供实证。完整报告见 `loadtest/README.md`。踩坑：k6 v2 移除内置 SSE 模块，最终用 `http.post` 完整消费流（`timings.waiting`=首字节，事后解析 SSE 响应体），零扩展依赖

## [0.3.0] - 2026-08-27

### 新增

- **🧪 分层测试体系（pytest）**：46 个用例秒级回归——单元层（视图裁剪轮次边界/Token 聚合双来源/错误码注册表完整性/RFC 9457 构造）+ 图逻辑层（MemorySaver + Fake 组件替换全部 LLM 依赖，覆盖质量门控三路径、草稿不入对话历史、意图路由、HITL interrupt/resume）+ API 集成层（httpx 黑盒打真实路由：认证链路/RFC 9457 错误契约/SSE 事件序列/traceId 中间件，独立 legal_db_test 测试库每用例重建，PG 不可达自动 skip）；`backend/tests/` 分层组织，`uv run pytest tests` 一键运行
- **🐳 全栈容器化部署**：`backend/Dockerfile`（uv 多阶段构建，仅携带虚拟环境+源码）+ `frontend/Dockerfile`（Node 构建 → nginx 托管 SPA）+ `nginx.conf`（SPA 路由回退 + `/api` 反代，SSE 关闭缓冲）；`docker-compose.yml` 通过 profiles 区分环境——开发 `up -d` 只起数据库，部署 `--profile prod up -d --build` 全栈拉起（postgres healthcheck → backend → frontend 依赖编排），Chroma/BM25 索引与 Embedding 模型走宿主机 volume 持久化
- **🧹 Context 管理 — 视图裁剪 + 自动摘要压缩（防 Context 爆炸）**：checkpoint 全量保留 messages（HITL resume 依赖），LLM 输入走视图裁剪（字符预算 6000，轮次边界对齐，当前问题永不丢）；落入裁剪区的内容超 2000 字触发一次 LLM 增量摘要压缩（结构化事实提取：金额/期限/法条/时效），摘要存 `state.context_summary` + `summarized_count` 游标持久化，下轮只压新增量；`_qa_node` 与 `info_gathering` 两个接入点。E2E：32 条消息 16041 字 → 摘要覆盖前 26 条且关键事实零丢失，3 轮对话无回归
- **🔗 LCEL 统一管道重构（QA Agent）**：`qa_agent.py` 收敛为三条 LCEL 链——`qa_chain`（RunnableLambda 组装消息 | llm，ainvoke/astream 统一走管道）、`summarize_chain`（PromptTemplate | llm | StrOutputParser）、`meta_chain`（预处理 | meta_llm）；消息组装/模板渲染自动进 LangSmith trace，输出保持 AIMessageChunk 流式语义不变
- **🪞 Self-Reflection 质量门控（生成-评估-修正循环）**：qa_generation 后新增 `quality_gate` 节点，评审 LLM 按清单自评（忠实性一票否决/针对性/可操作性），不通过带反馈重试（`REFLECTION_MAX_ROUNDS` 封顶）；草稿不入对话历史，`revision` 复位事件贯穿 API/前端清空第一版草稿；评审失败与重试额度用尽均降级放行，`REFLECTION_ENABLED` 开关可关
- **💰 Token 成本追踪（Custom Callbacks）**：`BaseCallbackHandler.on_llm_end` 采集每次 LLM 调用的用量 → 带 traceId 结构化日志（模型名/in/out/total/成本估算/延迟）；ContextVar 桥接纯 ASGI 中间件的 traceId；挂载在模型构造参数，方法代理零影响
- **📊 Token 用量全链路呈现**：请求级累计器（`RequestUsage` + ContextVar，一次请求所有 LLM 调用自动归集）→ SSE `usage` 事件（interrupt 打断的对话同样照发）→ `chat_messages.usage JSONB` 落库（迁移 `0003_add_message_usage`）→ 前端消息下方展示"消耗 N tokens（输入/输出/调用次数）"。E2E 验证 SSE/DB/API 三处数据一致
- **📡 分阶段事件推送（Stream Mode 多路复用）**：`stream_mode=["messages", "updates"]` 同时订阅 token 流与节点完成增量，workflow 层归一化 `token`/`stage` 两类事件——SSE 实时推送"正在理解您的问题 → 识别为：法律咨询 → 正在检索相关案例 → 找到 N 条相关案例 → 正在生成回答"进度（running/done 状态），前端渲染进度行、正文输出后自动隐藏；interrupt 检测逻辑零改动
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
