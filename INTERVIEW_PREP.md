# LegalMind 面试准备手册（汉得 AI 应用研发工程师）

> 本文档逐条对应 JD 要求，每节带代码跳转位置，面试可直接引用。
> 代码路径基准：`backend/app/`

---

## 一、Agent 架构全景（JD: Agent 任务编排/工具调用/执行链路）

### 1.1 整体编排图

```
用户输入
  → 意图识别（LLM + 结构化输出 + 置信度）
  → HITL #1 意图确认（置信度 < 0.8 时 interrupt）
  → info_gathering（自循环，最多 3 轮追问）
  → HITL #2 多轮信息收集（不足时 interrupt）
  → [层级 Agent 团队] domain_supervisor → specialist（并行）→ combiner
  → retrieval_agent（ReAct 子图，BM25+向量+Reranker）
  → HITL #3 检索不充分补充（自动重试耗尽后 interrupt）
  → QA 生成（流式）
  → quality_gate（Self-Reflection 质量门控）
  → (不通过 → 反馈注入 → 重试) / (通过 → final_output)
```

**图编排代码**：[workflow.py `_build_graph`](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/workflow.py#L67-L139)

**状态定义**：[workflow.py `AgentState`](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/workflow.py#L29-L56)

### 1.2 三处 HITL 中断点

| # | 节点     | 触发条件                    | 代码位置                                                                                                                                                   |
| - | -------- | --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | 意图确认 | `intent_confidence < 0.8` | [human_loop.py `check_intent` L17-49](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/human_loop.py#L17-L49)                |
| 2 | 多轮追问 | LLM 判定信息不充分          | [human_loop.py `info_gathering` L66-132](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/human_loop.py#L66-L132)            |
| 3 | 检索补充 | 自动重试 2 轮仍不足         | [retrieval_agent.py `evaluate_node` L185-243](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/retrieval_agent.py#L185-L243) |

**面试话术**：

> "三处 HITL 共享同一设计原则——interrupt 是有条件触发的，不是无脑打断。信息收集节点的兜底逻辑是：LLM 失败降级放行、空追问降级放行、只有'确实不充分且有问题可问'才 interrupt。判断是增强体验，不是关键路径，宁可少追问一轮也不能阻塞回答。"

---

## 二、info_gathering 是干嘛的（面试常问）

### 2.1 作用

**info_gathering 是多轮信息收集节点**——在用户提问后、检索前，用 LLM 判断"当前对话信息是否足以回答"。不足则生成针对性追问，通过 `interrupt()` 暂停图执行，等用户补充后再继续。

**为什么需要**：法律咨询高度依赖事实细节（时间、金额、当事人关系）。用户第一句往往模糊（"我被公司开除了怎么办"），但追问一轮后可能补出关键信息（"被口头辞退，没签劳动合同，工作 8 个月"），直接影响适用法条和检索方向。

### 2.2 代码位置

- 节点定义：[human_loop.py `info_gathering` L66-132](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/human_loop.py#L66-L132)
- 图边连接（自循环）：[workflow.py L97-101](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/workflow.py#L97-L101) — `info_sufficient=False → 回自己；True → 按意图路由`
- Prompt 模板：[prompts.py `INFO_GATHERING_PROMPT`](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/llm/prompts.py#L106-L125)

### 2.3 自循环机制

```python
# workflow.py L97-101
workflow.add_conditional_edges("info_gathering", self._route_after_info, {
    "qa": "domain_supervisor",      # 信息充分 → 走检索
    "search": "domain_supervisor",
    "document": "document_generation",
    "loop": "info_gathering",       # 信息不足 → 自循环回自己
})
```

**防死循环**：`MAX_CLARIFY_ROUNDS = 3`（[human_loop.py L63](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/human_loop.py#L63)），超过强制放行。

### 2.4 三条出口路径（降级优先于打断）

| 路径        | 条件                                  | 动作           | 代码行                                                                                                           |
| ----------- | ------------------------------------- | -------------- | ---------------------------------------------------------------------------------------------------------------- |
| ① LLM 崩了 | ainvoke 抛异常 / 返回 None            | 降级放行       | [L104-108](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/human_loop.py#L104-L108) |
| ② 信息够   | `sufficient=True` 或 question 为空  | 放行           | [L114-115](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/human_loop.py#L114-L115) |
| ③ 信息不够 | `sufficient=False` 且 question 非空 | interrupt 打断 | [L118-122](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/human_loop.py#L118-L122) |

---

## 三、Self-Reflection 质量门控（三维清单 + 忠实性一票否决 + 重试上限）

### 3.1 是什么

**质量门控是生成后的自检环节**——QA 生成完回答后，不直接给用户，先让另一个 LLM 按清单评审，不通过则带反馈重试。

### 3.2 三维清单自评

评审 Prompt 在 [prompts.py `REFLECTION_PROMPT` L156-175](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/llm/prompts.py#L156-L175)：

| 维度                       | 评估内容                                         | 判定规则                                |
| -------------------------- | ------------------------------------------------ | --------------------------------------- |
| **忠实性（最重要）** | 回答是否基于检索案例？有没有编造法条/案号/事实？ | 编造 →**一律不通过**（一票否决） |
| **针对性**           | 是否正面回应用户问题？有没有答非所问？           | 轻微不足 → 可通过，feedback 指出       |
| **可操作性**         | 是否给出明确的下一步行动建议？                   | 轻微不足 → 可通过，feedback 指出       |

### 3.3 忠实性一票否决

法律场景对编造法条"零容忍"——回答里出现一条不存在的法条号，可能导致用户据此维权失败。所以忠实性问题**无论其他维度多好，一律判不通过**。

### 3.4 重试上限

| 配置     | 值                             | 代码位置                                                                                     |
| -------- | ------------------------------ | -------------------------------------------------------------------------------------------- |
| 门控开关 | `REFLECTION_ENABLED = True`  | [config.py](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/config.py) |
| 最大重试 | `REFLECTION_MAX_ROUNDS`      | [config.py](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/config.py) |
| 分数阈值 | `REFLECTION_SCORE_THRESHOLD` | [config.py](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/config.py) |

**门控节点**：[workflow.py `_quality_gate_node` L192-221](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/workflow.py#L192-L221)

```python
# 核心逻辑（workflow.py L209-221）
if not verdict.passed and round_used < settings.REFLECTION_MAX_ROUNDS:
    # 不通过 + 还有额度 → 带反馈回 qa_generation 重新生成
    return {"reflection_feedback": verdict.feedback, "reflection_round": round_used + 1}
# 通过 / 额度用尽 → 放行（答案总得给用户）
return {"messages": [AIMessage(content=response)], "reflection_passed": True}
```

### 3.5 草稿不入对话历史

关键设计：QA 生成节点**不写 messages**，最终版由 quality_gate 放行时统一写入。

```python
# workflow.py L182-183（qa_generation 节点注释）
# 注意：此处不写 messages（草稿可能被门控打回重来），
# 最终版由 quality_gate 节点在放行时统一写入对话历史
```

**为什么**：草稿如果写入 messages，重试时 LLM 会看到上一版（被判定不合格的回答）在历史里，可能复制错误。草稿不入历史 = 多轮一致性保证。

### 3.6 分数线兜底

[qa_agent.py `reflect_answer` L136-138](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/qa_agent.py#L136-L138)：

```python
# LLM 说 passed 但分低于阈值 → 仍不通过（防评审宽松漂移）
if verdict.passed and verdict.score < settings.REFLECTION_SCORE_THRESHOLD:
    verdict.passed = False
```

---

## 四、RAG 检索全链路（JD 核心）

### 4.1 两层架构：粗召回 + 精排

```
粗召回（retriever.py）                    精排（reranker.py）
────────────────────                     ──────────────────────
向量 20 条 + BM25 20 条                    cross-encoder 把 query+doc
        ↓                                 一起喂模型逐对精算相关性
RRF 融合排序（0.4/0.6 加权）                     ↓
        ↓                                 阈值 0.05 过滤噪声
后置 filters 过滤                                ↓
        ↓                                 最终 3-6 条进 prompt
返回 top 10 候选 ──────────────→
```

### 4.2 粗召回代码

**入口**：[retriever.py `retrieve` L182-217](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L182-L217)

**两路并行**：[retriever.py L196-202](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L196-L202)

```python
vector_coro = self._vector_search(query, filters)
if self.bm25_retriever:
    bm25_coro = asyncio.to_thread(self.bm25_retriever.invoke, query)
    vector_docs, bm25_docs = await asyncio.gather(vector_coro, bm25_coro)
```

**RRF 融合**：[retriever.py `_rrf_fusion` L26-50](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L26-L50) — `score(d) = Σ weight_i / (k + rank_i(d))`，BM25 权重 0.4，向量权重 0.6

### 4.3 后置过滤的位置

**后置过滤在 RRF 融合之后、返回 top_k 之前**：

[retriever.py L213-215](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L213-L215)：

```python
# 后置过滤（兜底：对 BM25 结果和向量结果做统一过滤）
if filters:
    docs = [doc for doc in docs if self._matches_filter(doc.metadata, filters)]
```

**后置过滤支持的运算符**：[retriever.py `_matches_filter` L122-165](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L122-L165)

- 简单等值：`{"court": "最高法院"}`
- `$contains`：`{"laws": {"$contains": "合同法"}}`（字符串子串 / 列表元素）
- `$in`：`{"category": {"$in": ["劳动争议", "合同纠纷"]}}`
- `$neq`：`{"court": {"$neq": "某法院"}}`
- `$year`：`{"judgment_date": {"$year": 2023}}`（日期前缀匹配）

**关键设计——简单过滤下推 vs 复杂过滤后置**：[retriever.py `_is_simple_filter` L117-120](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L117-L120) — 简单等值直接下推 Chroma `filter` 参数，复杂运算符走后置兜底。

### 4.4 精排代码

**Reranker**：[reranker.py](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/reranker.py)

- 模型：`BAAI/bge-reranker-v2-m3`（CrossEncoder）
- `max_length=256`（控制推理开销，[reranker.py L29](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/reranker.py#L29)）
- 同步 CPU 推理扔线程池：`asyncio.to_thread`（[reranker.py L79](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/reranker.py#L79)）
- 去重：同 title 只保留最高分 chunk（[reranker.py L88-97](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/reranker.py#L88-L97)）

**阈值过滤**：[retrieval_agent.py L85-89](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/retrieval_agent.py#L85-L89)

```python
if settings.RAG_SCORE_THRESHOLD > 0:
    ranked_results = [
        c for c in ranked_results
        if (c.get("rerank_score") or 0) >= settings.RAG_SCORE_THRESHOLD  # 0.05
    ]
```

**为什么需要阈值**：实测三档分布——强相关 0.55-0.99 / 法条语义相关 0.05-0.5 / 噪声 ≤0.04。不设阈值时离谱查询也硬凑 top_k 条噪声 → LLM 拿噪声硬答（幻觉温床）。返回空列表 = 上层走"无参考"兜底。

### 4.5 检索质量实测数据

| 指标              | 数值                   | 测试方法                                    |
| ----------------- | ---------------------- | ------------------------------------------- |
| Hit@5             | **95%**（19/20） | 自建评测集 149 条，gold 标注应引用法条/案例 |
| MRR@5             | **0.867**        | 首个正确结果排名倒数的平均值                |
| Faithfulness      | **0.957**        | RAGAS LLM-as-Judge，较基线 +0.14            |
| Answer Relevancy  | **0.964**        | RAGAS 反向生成问题 + embedding 相似度       |
| Context Precision | 0.683                  | RAGAS（新版口径）                           |
| Context Recall    | 0.367                  | 偏低系 gold 粒度未对齐（整部法 vs 按条）    |

**数据规模**：法条 4,310 条（21 部法律 + 18 部司法解释，24 领域）+ 案例 44 篇 → 向量库 4,429 chunks（law 4,310 + case 119）

---

## 五、幂等数据管道 + 统一 Chunk Schema

### 5.1 幂等是什么

**幂等 = 同一脚本跑 1 次和跑 N 次，结果完全一样**——重复执行不会产生重复数据。

**为什么必须幂等**：数据管道天然要重跑——中途断网、扩数据、改了切分逻辑、向量库重建，都得把导入脚本再跑一遍。不幂等的后果：跑 3 次入库 3 遍 → 法条重复 → 检索返回 3 条一模一样的结果 → 排序被垃圾占位。

### 5.2 幂等实现

导入脚本在执行前先 count，已有数据直接 skip；`bulk_create(ignore_conflicts=True)`，主键冲突静默跳过。

### 5.3 Chunk 是什么

**Chunk = 把长文档切成可检索的短段落**。

为什么要切：法律文档太长（一部民法典 200+ 条），如果整部法律作为一个文档入库，检索时返回的是整部法律——LLM 拿到 10 万字上下文，成本爆炸且精度差。切成 chunk 后，检索命中"第 47 条"那一条，LLM 只看几百字。

### 5.4 分块策略

| 类型 | chunk_size | chunk_overlap | 代码位置                                                                                                                  |
| ---- | ---------- | ------------- | ------------------------------------------------------------------------------------------------------------------------- |
| 案例 | 500 字     | 50 字         | [build_index.py L29-33](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/scripts/build_index.py#L29-L33) |
| 法条 | 1000 字    | 100 字        | [build_index.py L60-63](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/scripts/build_index.py#L60-L63) |

切分器：`RecursiveCharacterTextSplitter`，分隔符优先级 `["\n\n", "\n", "。", "；", "，", " "]`

### 5.5 统一 Chunk Schema

**两类异构文档映射进同一套 metadata schema**，下游检索/重排/生成只认统一 schema，不关心数据从哪个源来。

| 字段          | 法条（law）  | 案例（case）              |
| ------------- | ------------ | ------------------------- |
| type          | `"law"`    | `"case"`                |
| id            | law.id       | case.id                   |
| title         | 法条标题     | 案例标题                  |
| content       | 条文正文     | case.content              |
| category      | law.category | —                        |
| keywords      | law.keywords | —                        |
| case_number   | —           | case.case_number          |
| court         | —           | case.court                |
| judgment_date | —           | case.judgment_date        |
| summary       | —           | case.summary              |
| laws          | —           | case.laws（相关法条列表） |

**构建代码**：[build_index.py L41-83](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/scripts/build_index.py#L41-L83)

**消费端按 type 分流**：[qa_agent.py `_format_cases` L190-226](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/qa_agent.py#L190-L226) — 法条回退注入 `content` 字段条文原文（截断 400 字），案例注入元数据级紧凑摘要。

---

## 六、上下文管理（JD: 上下文管理）

### 6.1 视图裁剪 vs 物理裁剪

**核心决策**：checkpoint 里的 messages 原样保留（HITL resume 依赖完整 state），只在构造 LLM 输入时做"视图裁剪"——超预算的最老轮次**原文**不进 prompt。

⚠️ 复习别记偏：**原文不进 ≠ 凭空消失**。被裁轮次后续由 6.2 压缩成摘要放回 prompt（见下）；没超预算时全量原文正常进 prompt、无需摘要。裁剪只负责"划边界"，边界外的信息保全是摘要的事。

**裁剪代码**：[context_manager.py `split_history` L22-56](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/llm/context_manager.py#L22-L56)

```python
# 从最新往回保留完整轮次，预算 6000 字
for j in range(1, n):
    if isinstance(msgs[j], HumanMessage) and suffix[j] <= budget:
        return msgs[j:], msgs[:j]  # 返回 (kept, dropped)
```

### 6.2 增量摘要压缩

被裁掉的最老轮次用 LLM 压缩成结构化事实摘要，**放回 prompt 的最前面**（摘要在前 = 更早的对话，近期原文在后 = 更精确），下一轮复用不重复压缩。

**最终 prompt 结构**（[qa_agent.py `build_messages` L113-120](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/qa_agent.py#L113-L120)）：

```
system（人设 + 检索案例）
→ 【早期对话摘要】← 被裁轮次压缩后回填这里
→ 近期对话原文（split_history 的 kept）
```

**摘要 Prompt**：[prompts.py `HISTORY_SUMMARIZE_PROMPT` L140-153](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/llm/prompts.py#L140-L153) — 必须保留金额/期限/当事人等结构化事实

**增量摘要逻辑**：[workflow.py L154-165](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/workflow.py#L154-L165)

```python
# 裁剪区中尚未入摘要的段落 = msgs[summarized_count : 裁剪区终点]
new_dropped = all_msgs[summarized_count:cut]
# 累积到阈值才触发摘要 LLM（小额裁剪不值得一次调用）
if estimate_chars(new_dropped) >= settings.SUMMARY_TRIGGER_CHARS:
    summary = await self.qa_agent.summarize_history(summary, new_dropped)
    summarized_count = cut
```

两个边界情况（面试追问防身）：

- **悬空期**：新裁段落累积未达 `SUMMARY_TRIGGER_CHARS` 时，既不在原文也不在摘要——物理还在 checkpoint，不算丢，是省 LLM 调用的权衡
- **失败降级**：摘要 LLM 挂了 → 降级"仅裁剪、无压缩"（[qa_agent.py L165-167](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/qa_agent.py#L165-L167)），主流程不阻塞

### 6.3 Token 全链路追踪

```
LLM 回调 → ContextVar（请求级隔离）→ SSE（实时推送）→ PostgreSQL JSONB（可查询持久化）→ 前端展示
```

**定义**：`usage_tracker.py` 模块级 ContextVar
**写入**：纯 ASGI 中间件（最外层起点）
**读取**：LangChain callback `on_llm_end`（累加 token）+ SSE 端点

**实测数据**：完整链路 8 次 LLM 调用均值 15,640 tokens / 轻路径（寒暄）524 tokens

---

## 七、测试中遇到的问题（面试 STAR 回答素材）

### 7.1 问题一：短查询案例召回为空（检索层 bug）

**现象**：用户搜"拖欠工资"，案例搜索结果为 0，但库里明明有劳动争议案例。

#### 7.1.1 先搞清楚："召回"是哪一步、链路是什么

读取路全链路（复习背这条）：

| 步骤 | 干什么                                  | 代码位置                                                                                                                                        |
| ---- | --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | query embedding                         | Chroma 内部（查询时向量化）                                                                                                                     |
| 2    | **双路召回并行**：向量 ANN + BM25 | [retriever.py L196-202](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L196-L202)（`asyncio.gather`） |
| 3    | RRF 融合排序                            | [retriever.py L204-211](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L204-L211)                       |
| 4    | 后置过滤（兜底）                        | [retriever.py L213-215](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L213-L215)                       |
| 5    | 返回 top 候选给上层                     | [retriever.py L217](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L217)                                |
| 6    | 精排 rerank（cross-encoder）            | [retrieval_agent.py L75-80](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/retrieval_agent.py#L75-L80)            |
| 7    | rerank 阈值过滤（0.05）                 | [retrieval_agent.py L85-89](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/retrieval_agent.py#L85-L89)            |

**"召回" = 第 2-4 步（粗召回）**，发生地在 [retriever.py `retrieve` L182-217](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L182-L217)。向量检索完不是直接精排——中间还有 RRF 融合和后置过滤，然后才进 reranker。

#### 7.1.2 核心概念澄清：「过滤下推」≠ 先检索再过滤（我当时的疑问）

疑问："下推到 Chroma？Chroma 不是先检索的吗？"

**正确理解**：下推是**把 filter 作为 Chroma 查询参数传进去**（`asimilarity_search(query, k, filter=filters)`），Chroma 在做 ANN 搜索时就只在该类型的子集上搜——**过滤是检索语句的一部分，和检索同时发生**，不是检索完再筛。类比 SQL：`WHERE type='case' ORDER BY embedding LIMIT 40` 写在查询里让数据库执行，而不是先 `LIMIT 40` 拉回来程序再 WHERE——后者顺序反了，结果必错。

**修改前后对比**：

```
修改前（bug）：                         修改后（fix）：
Chroma 无 filter 检索全局 top-40         filter={"type":"case"} 传进查询
法条 4310 条 vs 案例 44 条                ↓
短查询候选池 40 条全被法条占满             Chroma 在案例子集上做 ANN
        ↓                                候选池从一开始就只有案例
代码拿到结果后再过滤 type=case                    ↓
= 在"没有案例的池子"里筛案例 → 0 条        案例正常进候选池
```

#### 7.1.3 根因定位

写了诊断脚本分别测原始召回和过滤后结果，发现混合召回本身正常——根因是**文档类型过滤做在了召回之后**：短查询语义宽泛，BM25+向量的候选池被 4,310 条法条占满，44 篇案例挤不进 top-20 候选，后置过滤再筛 case 类型自然为 0。

#### 7.1.4 修改点详解（改了哪、为什么）

**修改点 1：调用层把 doc_type 并进召回参数** — [retrieval_agent.py L63-66](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/retrieval_agent.py#L63-L66)

```python
recall_filters = dict(filters or {})
if doc_type:
    recall_filters.setdefault("type", doc_type)
candidates = await self.retriever.retrieve(query=query, top_k=top_k * 3, filters=recall_filters)
```

**为什么**：`doc_type` 原来只在召回后过滤（L72-73）。改后让它混进 `recall_filters` 跟着召回一路传下去，才有机会被下推。`top_k*3` 多取 3 倍候选给精排留余量。

**修改点 2：检索层把简单过滤下推到 Chroma** — [retriever.py `_vector_search` L167-180](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L167-L180)

```python
if filters and self._is_simple_filter(filters):
    try:
        return await self.vector_store.asimilarity_search(
            query, k=settings.RAG_TOP_K * 2, filter=filters
        )
    except Exception:
        pass  # 下推失败 → 退回无过滤检索，交后置兜底
```

**为什么只下推"简单等值"**：[retriever.py `_is_simple_filter` L117-120](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L117-L120) 判断所有值都不是 dict（即不含 `$contains/$in/$neq/$year` 运算符）才下推——Chroma 原生 where 语义和这些自定义运算符不完全一致，复杂条件下推会错筛，留后置做。

**保留的两道兜底（为什么不能删）**：

1. [retriever.py L213-215](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/rag/retriever.py#L213-L215)：**BM25 那一路必须靠它**——rank_bm25 是内存索引，`invoke(query)` 不支持 filter 参数，案例过滤只能召回后做
2. [retrieval_agent.py L72-73](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/retrieval_agent.py#L72-L73)：防 Chroma 下推失败（字段类型不支持等异常走 `except: pass`）时类型混入

**验证**：同样"拖欠工资"查询案例召回从 0 条恢复到 2 条，场景子集 Hit@5 最终 95%。

**面试话术**：

> "过滤条件的位置（召回前 vs 召回后）在候选池有限时会改变结果集，这是混合检索特有的坑——候选池被单一类型占满时，后置过滤等于空过滤。所谓下推，就是把 filter 写进 Chroma 的查询参数，让类型过滤在 ANN 搜索阶段同时完成；BM25 那路因为内存索引不支持 filter，保留后置过滤兜底。"

### 7.2 问题二：法条正文丢失导致幻觉

**现象**：RAGAS 首测 Faithfulness 只有 0.82，模型回答法条依据含糊。

**定位**：检查注入 prompt 的文本发现 `_format_cases` 只读案例元数据的 `summary/laws` 字段，但法条 chunk 的元数据**没有这两个字段**——条文正文存在 `content` 里被整个丢弃了，LLM 只看到法条标题，靠参数记忆补内容 → 幻觉。

**修复**：按 `type` 分流渲染，法条 chunk 回退注入 `content` 字段的条文原文（截断 400 字）。

**代码位置**：[qa_agent.py `_format_cases` L190-226](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/qa_agent.py#L190-L226)

```python
if case.get("type") == "law":
    content = (case.get("content") or "").strip()
    formatted.append(
        f"【法条{i}】\n"
        f"名称：{case.get('title', '未知')}\n"
        f"条文：{content[:400] if content else '未知'}\n"
    )
```

**验证**：修复后 RAGAS 复测 Faithfulness 0.957（+0.14）、Answer Relevancy 0.964。

**面试话术**：

> "幻觉治理不能只靠 prompt 要求'别编造'，喂进去的上下文本身错了，再强的门控也救不回来。"

### 7.3 问题三：HITL 中断陷入循环

**现象**：检索结果不足时系统最多允许 3 轮人工追问，用户被反复打断，卡片文案暴露内部轮次。

**修复**：

1. `MAX_INTERRUPT_ROUNDS` 降为 1（[retrieval_agent.py L147](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/retrieval_agent.py#L147)）
2. 降级原则——判断类节点失败一律放行而非阻塞（[human_loop.py L104-108](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/human_loop.py#L104-L108)）
3. 文案重写为用户视角（[retrieval_agent.py L221-230](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/retrieval_agent.py#L221-L230)）

### 7.4 问题四：score 字段恒 0

**现象**：`cases/search` API 返回的 `score` 字段恒为 0。

**定位**：`_doc_to_dict` 读 `metadata["score"]`，但向量库无此元数据 → 恒 0。

**修复**：rerank 后回写 `score` 字段：[retrieval_agent.py L93-94](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/retrieval_agent.py#L93-L94)

```python
for c in ranked_results:
    c["score"] = c.get("rerank_score", 0)
```

---

## 八、高并发与工程稳定性（JD: 稳定性/可扩展性）

### 8.1 背压控制

LLM API 有 RPM/TPM 限额，高并发下无限制打过去触发限流甚至雪崩。用 `asyncio.Semaphore` 进程级信号量控制并发 in-flight 请求数，主备共享额度，流式全程持有许可。

### 8.2 多级缓存

- L1 进程内 LRU：零网络开销扛热点
- L2 Redis cache-aside：跨进程共享
- 熔断降级：Redis 挂了自动降级到 LRU 再到直查
- 失败降级值**绝不写缓存**（否则一次网络抖动固化错误结果 24h）

**缓存使用**：

- 意图识别缓存：[intent_agent.py L57-69](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/intent_agent.py#L57-L69) — `INTENT_CACHE_TTL=24h`
- 检索结果缓存：[retrieval_agent.py L52-58](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/retrieval_agent.py#L52-L58)

### 8.3 异步非阻塞

- 全链路 asyncio
- BM25 CPU 计算 + Chroma 同步 API → `asyncio.to_thread` 扔线程池
- 两路检索 `asyncio.gather` 并行 → 总耗时 = max(两路)
- 纯 ASGI 中间件（非 BaseHTTPMiddleware）—— 后者破坏 SSE 断连检测

### 8.4 压测数据

| 指标           | 数值    |
| -------------- | ------- |
| 基础设施层 QPS | 458.39  |
| p95            | 2.09ms  |
| 请求总数       | 82,592  |
| 失败率         | 0.00%   |
| 流式首事件 p90 | 43.83ms |
| 流式整流 p90   | 43.99s  |
| 206 路并发     | 零失败  |

### 8.5 可观测性

- RFC 9457 全局错误规范
- X-Request-ID 全链路追踪
- LLM 双实例 Fallback 容灾
- 88 个分层测试接 GitHub Actions CI（lint + 测试双闸门）

---

## 九、MCP 协议突击准备（JD 重点，项目短板）

### 9.1 核心概念

MCP（Model Context Protocol）是 Anthropic 2024 年 11 月发布的开放协议，解决 AI 应用与外部工具/数据源之间的 N×M 集成问题。

- 没有 MCP：10 个应用 × 20 个工具 = 200 套适配代码
- 有了 MCP：10 + 20 = 30 套

三个角色：Host（AI 应用）→ Client（翻译官）→ Server（暴露工具能力）

最强特性：**动态工具发现**——Agent 启动时扫描 MCP Server，运行时自动获得新能力，不需要重新部署代码。

### 9.2 MCP vs Function Calling

|      | Function Calling                          | MCP                              |
| ---- | ----------------------------------------- | -------------------------------- |
| 层次 | 模型层能力                                | 传输层协议                       |
| 作用 | LLM 输出结构化 JSON 指令                  | 规范工具发现/调用/返回的完整通信 |
| 本质 | 模型决定"调什么"                          | 应用如何"连接工具"               |
| 关系 | 互补：Agent 用 FC 决定调用，通过 MCP 执行 |                                  |

### 9.3 三个原语

- **Tools**：模型主动调用（有副作用，如查余额、提交申请）
- **Resources**：应用层读取（无副作用，如读文件、读配置）
- **Prompts**：预定义的 prompt 模板

### 9.4 项目中如何回答

> "我项目里目前还没有正式集成 MCP——LegalMind 的工具调用是直接用 LangChain 的 @tool 装饰器 + Function Calling 实现的。但我研究过 MCP 的设计，也在升级计划里规划了将 search_cases 工具 MCP 化——封装成 MCP Server 后，同一个法律检索能力可以被 Claude Desktop、Cursor 等任何支持 MCP 的 Host 复用。当前不用 MCP 的原因是工具数量少（1 个检索工具），直接用 LangChain 内置机制更简单；但如果未来要接入多数据源（裁判文书网 API、法律法规库 API），MCP 的统一接口和动态发现就有价值了。"

### 9.5 MCP 高频追问

| 问题            | 回答要点                                           |
| --------------- | -------------------------------------------------- |
| 安全风险        | 恶意 Server 供应链攻击 → 白名单 + 沙箱 + 审计日志 |
| 上下文爆炸      | 工具描述太长挤占 token → 按需加载                 |
| MCP 和 A2A 区别 | MCP 是应用↔工具，A2A 是 Agent↔Agent              |
| 通信方式        | stdio（本地）+ HTTP/SSE（远程）                    |
| 谁提出的        | Anthropic，2024 年 11 月                           |

---

## 十、ReAct 检索子图（JD: Agent 工具调用）

### 10.1 子图结构

```
agent（LLM 推理 + 工具调用决策）
  → tools（ToolNode 执行 search_cases）
  → evaluate（评估结果数量）
  → retry（不足 → 回 agent）/ finish（足够 → 返回主图）
```

**编译代码**：[retrieval_agent.py `build_retrieval_subgraph` L257-276](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/retrieval_agent.py#L257-L276)

### 10.2 ReAct 循环

```python
# agent_node：LLM 分析 query → 决定调用 search_cases 的参数
response = await llm.ainvoke(invoke_messages)  # L186
# tools_condition 路由：有 tool_calls → tools，无 → finish
# evaluate_node：评估检索结果数量
if count >= 3:
    return {"retrieved_cases": cases, "status": "done"}  # L199
if retry < 2:
    return {"status": "retry", "messages": [反思反馈]}   # L206
# 自动重试耗尽 → HITL interrupt
user_supplement = interrupt({...})  # L221
```

### 10.3 三层工具校验

1. **LLM 层**：Function Calling 参数校验（Pydantic schema 约束）
2. **ToolNode 层**：`handle_tool_errors=True` 自动捕获工具异常
3. **evaluate 层**：结果数量评估 + 反思反馈注入

---

## 十一、层级 Agent 团队（JD: 任务编排）

### 11.1 架构

```
domain_supervisor（识别法律领域，1-2 个）
  → Send fan-out → specialist（每个领域一个专家，并行检索）
  → combiner（合并去重，不足则升级 ReAct 兜底）
```

### 11.2 代码位置

- Supervisor：[supervisor.py `domain_supervisor_node`](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/supervisor.py)
- Specialist：[supervisor.py `specialist_node`](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/supervisor.py)
- Combiner：[supervisor.py `combiner_node`](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/supervisor.py)
- 路由逻辑：[workflow.py L295-310](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/workflow.py#L295-L310)

### 11.3 Send API 并行

```python
# workflow.py L301-304
return [
    Send("specialist", {"domain": d, "query": state["query"]})
    for d in domains
]
```

**为什么用 Send 不用图边**：Send 是运行时动态 fan-out——领域数量由 LLM 决定（1-2 个），编译时无法确定路数。固定两路用 `gather` 即可（见 retriever.py）。

---

## 十二、面试高频问题速查（10 题）

| #  | 问题                         | 答案来源             |
| -- | ---------------------------- | -------------------- |
| 1  | RAG 完整链路                 | 第四章               |
| 2  | Agent 架构为什么用 LangGraph | 第一章 + workflow.py |
| 3  | 工具调用怎么实现 + 失败兜底  | 第十章               |
| 4  | MCP 了解吗 + 和 FC 区别      | 第九章               |
| 5  | 上下文窗口满了怎么办         | 第六章               |
| 6  | RAG 召回率低怎么排查         | 第 7.1 节            |
| 7  | Agent 死循环怎么防           | 第 7.3 节 + 业务守卫 |
| 8  | RAGAS 评测怎么做的           | 第四章 4.5           |
| 9  | 高并发怎么处理               | 第八章               |
| 10 | 线上最大 bug                 | 第 7.1 或 7.2 节     |
| 11 | 中断/崩溃后怎么恢复           | 第十四章 14.1        |
| 12 | 多轮对话状态怎么管理、怎么防跑偏 | 第十四章 14.2/14.3  |

---

## 十三、简历指标对照表（全部可复现）

| 指标                   | 数值              | 复现文件                            |
| ---------------------- | ----------------- | ----------------------------------- |
| 法条库                 | 4,310 条          | PostgreSQL`laws` 表               |
| 向量库                 | 4,429 chunks      | ChromaDB                            |
| Hit@5                  | 95%               | `backend/scripts/diag_recall.py`  |
| MRR@5                  | 0.867             | 评测集 149 条                       |
| RAGAS Faithfulness     | 0.957             | `backend/data/ragas_results.json` |
| RAGAS Answer Relevancy | 0.964             | 同上                                |
| k6 QPS                 | 458.39            | `loadtest/README.md`              |
| k6 p95                 | 2.09ms            | 同上                                |
| Token（完整链路）      | 15,640 / 8 次调用 | PostgreSQL JSONB                    |
| Token（轻路径）        | 524               | 同上                                |
| 分层测试               | 88 passed         | `pytest --cov=app`                |

---

## 十四、会话状态与中断恢复（面试新题）

### 14.1 崩溃/断线恢复——协作式中断 vs 故障中断

**核心辨析**：两类中断**共用同一 PostgresSaver checkpoint 存储**，差别只在触发者。

- **协作式中断**（HITL）：`interrupt()` 主动暂停，恢复时 `Command(resume=...)` 注入用户回答
- **故障中断**（进程崩溃/网络断连）：无新输入，恢复时 `astream_continue` 传 input=None 纯续跑（durable execution）

**判断只用两个字段**：`state.next` 回答"**有没有**没做完的节点"（LangGraph 每 superstep 把下一批节点名写进 checkpoint，跑完为空）；`tasks[0].interrupts` 回答"**为什么**没做完"（HITL 带 payload，故障中断没有）。组合三场景：next 空→无事可做（409）；next 非空+interrupts→HITL 卡片接管；next 非空+无 interrupts→显示「继续生成」按钮。

**代码位置**：[workflow.py `astream_continue`](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/agents/workflow.py#L487-L497) · [chat.py `/continue` + `/pending` 端点 + `_check_pending`](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/backend/app/api/chat.py#L91-L107) · 前端 [stores/chat.js `probePending`](file:///c:/Users/yhs/Desktop/Legal/RAG_langgrpah-legalMind/frontend/src/stores/chat.js)（双探测时机：loadMessages 后=崩溃重启、sendMessage 异常 catch=网络波动）

**恢复正确性四保障（面试加分点）**：
1. 归属校验先行——`_get_owned_session` 防"读取到别人的任务"
2. 恢复位置不用自己算——input=None，LangGraph 从最近 checkpoint 的 pending 节点续跑
3. **恢复粒度=节点边界**——执行到一半的节点整体重跑，token 级续传不存在（诚实说边界）
4. 幂等两道闸——消息层 add_messages 按 id 去重；落库层 `_finalize_stream` 只在流收尾跑一次

> **话术**："本项目副作用只有只读检索、可重跑的 LLM 生成、流收尾落库（不在图节点内），天然幂等——这是按业务形态裁剪的结果，不是没做幂等设计；如果换成下单/发消息类副作用，就要上 operation_id 幂等键 + planned/succeeded/unknown 三态核对。"

### 14.2 会话状态四分法（信息类型/生命周期口径）

| 类型 | 本项目实现 | 生命周期 |
| --- | --- | --- |
| 对话历史 | 滑窗裁剪+增量摘要+寒暄 RemoveMessage 擦除 | 当前会话 |
| **业务状态** | **案情简报**（party/claim/key_facts/focus，只记用户明确确认的事实） | 当前任务 |
| **任务状态** | 重试施工单+HITL 追问+反思轮次 | 一次执行 |
| 长期记忆 | 用户主权 PostgresStore（前端自维护） | 跨会话 |

**LangGraph 边界**：框架管**状态的存取与恢复**（容器/reducer/快照/interrupt/续跑/get_state），不管**状态的语义与纪律**（谁抽取、何时失效、防跑偏、幂等、观测）——后者全是应用层的活。

### 14.3 防跑偏——三道防线自评（诚实版）

1. **结构化锚点** 🟡：简报.claim 每轮注入=锚点常在，但**注入≠核对**，没有节点拿它对照新消息
2. **进度核对** 🟡：质量门控查内容质量（忠实性/完整性），不查目标推进——忠实检索资料≠没跑偏
3. **事实来源+版本** 🟡：数字与原话一致+优先级链算来源纪律，无 state_version

**入口对齐有**（意图识别+HITL confirm_intent=开局理解），**逐轮防漂缺 → A8**（core_intent 锚点+新输入四分类+简报版本化，多轮会话才启用——按业务形态裁剪是加分答法）。

---

> **面试核心心态**：汉得是企业服务公司，面试官更关心**工程落地能力**——能不能把 Agent 做稳定、做可控、上线不出事。质量门控、HITL 降级、背压控制、压测基线全是这个方向。每个答案都落到"我用什么手段定位的"（诊断脚本、分层压测、检查注入文本），而不是"我猜是 XX 然后改好了"。
