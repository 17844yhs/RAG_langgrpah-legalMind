# k6 性能压测报告

> 脚本：[chat_stream.js](chat_stream.js) ｜ 压测日期：2026-09-03 ｜ 全部数字为 k6 实测，可复跑验证

## 一、压测对象与环境

| 项 | 值 |
| --- | --- |
| 被测系统 | LegalMind 后端单实例（uvicorn 2 worker，Windows 本机） |
| 基础设施 | Docker 容器：PostgreSQL + Redis |
| LLM | DeepSeek 上游 API（真实调用） |
| 压测工具 | k6 v2.2.0 |

## 二、测试流程（4 步）

```
① setup        注册压测专用账号（随机后缀防冲突）→ 拿 JWT token
② 加压         虚拟用户（VU）阶梯爬升：infra 20→50→100；chat 5→10→15
③ 执行         每个 VU 循环发请求：
                 infra 模式  → GET /health（空操作，立刻返回）
                 chat 模式   → POST /api/chat/stream，完整消费 SSE 流直到 [DONE]
④ 汇总         k6 统计 QPS / 延迟分位数（p90/p95）/ 错误率 / token 总量，
                 与 thresholds 及格线自动比对 → 通过 ✗/✓
```

**chat 模式一次迭代的完整链路**（和真实用户一模一样）：

```
登录态 POST /api/chat/stream
  → SSE 握手（session_id 事件）
  → 意图识别 → 并行混合检索（BM25+向量）→ rerank
  → LLM 流式生成（逐 token）→ 质量自检门控 → 元数据抽取
  → sources / usage / [DONE] 收尾
```

## 三、SSE 压测原理（零扩展依赖方案）

k6 v2 移除了内置 SSE 模块（`k6/experimental/sse` / `k6/sse` 均不存在），社区扩展 `k6/x/sse` 的自动 provisioning 需 Go 工具链。最终方案**零扩展**：

- `http.post` 会**完整消费流式响应**才返回 → 把 SSE 当普通响应读
- `timings.waiting`（首字节时间）≈ **首 SSE 事件延迟**（用户多久看到"开始响应"）
- `timings.duration` = **整条流总时长**（用户等完整答案的总时间）
- 响应体是完整 SSE 文本 → 正则提取 `usage`（token 归集值）、`error` 事件、`[DONE]`（正常收尾判定）

## 四、实测数字

### 4.1 infra 基础设施基线（GET /health，无 LLM，空白对照组）

| 指标 | 数值 |
| --- | --- |
| 吞吐（含 100ms think time） | **458 req/s** |
| 延迟 p95 / avg / max | **2.24ms / 1.01ms / 59.5ms** |
| 并发 | 100 VU × 3 分钟（20→50→100 阶梯） |
| 总请求 / 错误率 | 82,485 次 / **0%** |

阈值：`http_req_failed < 1%` ✅ `http_req_duration p(95) < 200ms` ✅

### 4.2 chat 真实业务链路（SSE 流式，RAG + LLM + 质量门控）

| 指标 | 数值 |
| --- | --- |
| 完整流数 / 失败数 | 206 条 / **0 失败** |
| 首 SSE 事件延迟（TTFB）avg / p90 / p95 / max | **28.3ms / 57.6ms / 81.1ms / 166ms** |
| 整条流总时长 avg / med / p90 / p95 / max | **8.41s / 7.56s / 13.8s / 16.8s / 24.9s** |
| 流式吞吐 @15 并发 | ≈ 0.88 条/s（53 条/min） |
| token 消耗 | 362,084 总计 / **≈1,758 tokens/条**（生成+元数据+质量自检全部 LLM 调用归集） |

阈值：`chat_stream_errors < 20%` ✅ `chat_stream_total_ms p(90) < 60s` ✅ `chat_first_event_ms p(90) < 15s` ✅

## 五、瓶颈分析与结论（面试叙事）

1. **对照实验设计**：infra（空白对照）vs chat（实验组）——应用栈 p95 仅 2.24ms、458 QPS，框架层贡献的延迟可忽略；13.8s 的流耗时**几乎全部在 DeepSeek 上游生成**（检索仅占 1-2s）
2. **优化方向由数据决定**：瓶颈在 LLM 侧 → 该做**语义缓存 / 限流排队**，而不是加 worker / 换框架——这正是路线图"多级缓存 + 限流熔断"两项的实证依据
3. **成本意识**：单条问答实测 1,758 tokens，缓存收益可以按钱算（命中一次省一次生成的钱）

## 六、复跑命令

```bash
# 前置：PG/Redis 容器运行 + 后端已启动（uvicorn :8000）
k6 run -e MODE=infra loadtest/chat_stream.js   # 基线，零成本
k6 run -e MODE=chat  loadtest/chat_stream.js   # 业务链路，烧真实 LLM token（约 30-40 万 token）
```

可选环境变量：`BASE_URL`（默认 `http://127.0.0.1:8000`）、`QUESTION`（默认"试用期最长可以约定多久？"）
