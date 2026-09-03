/**
 * k6 压测脚本 — LegalMind 法律咨询 Agent（零扩展依赖版）
 *
 * 两种模式（环境变量 MODE 切换，默认 chat）：
 *   MODE=infra  → 打 GET /health，测基础设施层吞吐（FastAPI/uvicorn/中间件栈，零 LLM 成本）
 *   MODE=chat   → 打 POST /api/chat/stream（SSE 流式），测真实业务链路（RAG + LLM + 门控）
 *                 低并发阶梯（5→10→15），控制 DeepSeek token 成本
 *
 * 用法：
 *   k6 run -e MODE=infra loadtest/chat_stream.js
 *   k6 run -e MODE=chat  -e BASE_URL=http://127.0.0.1:8000 loadtest/chat_stream.js
 *
 * SSE 压测原理（无需 k6 SSE 扩展）：
 *   k6 http.post 会完整消费流式响应体 ——
 *   - http_req_waiting（waiting）= 请求发出 → 首个响应字节 ≈ 首事件延迟（session_id 事件）
 *   - response.timings.duration  = 整条流的总时长
 *   - 响应体为完整 SSE 文本，可解析 usage / error / [DONE]
 *
 * 前置条件：
 *   1. 服务已启动（uvicorn :8000），PG/Redis 容器运行中
 *   2. setup() 自动注册/登录压测专用账号获取 token，无需手工准备
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const MODE = __ENV.MODE || 'chat';
const CHAT_QUESTION = __ENV.QUESTION || '试用期最长可以约定多久？';

// ── 自定义指标 ──
const chatFirstEventMs = new Trend('chat_first_event_ms', true); // 首事件延迟（waiting ≈ 首字节）
const chatStreamTotalMs = new Trend('chat_stream_total_ms', true); // 整条流的总时长
const chatStreamErrors = new Rate('chat_stream_errors'); // 非 200 / 流内 error / 未正常收尾
const chatTotalTokens = new Counter('chat_total_tokens'); // 压测期间消耗的总 token 数

// ── 场景定义 ──
const SCENARIOS = {
  // 基础设施基线：无 LLM，纯应用栈吞吐
  infra: {
    executor: 'ramping-vus',
    exec: 'infraScenario',
    stages: [
      { duration: '30s', target: 20 },
      { duration: '60s', target: 50 },
      { duration: '60s', target: 100 },
      { duration: '30s', target: 0 },
    ],
  },
  // 业务链路：SSE 流式 + LLM，低并发控成本
  chat: {
    executor: 'ramping-vus',
    exec: 'chatScenario',
    gracefulStop: '10s',
    stages: [
      { duration: '40s', target: 5 },
      { duration: '80s', target: 10 },
      { duration: '80s', target: 15 },
      { duration: '30s', target: 0 },
    ],
  },
};

const THRESHOLDS = {
  infra: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<200'], // 纯栈 health 检查，p95 应在毫秒级
  },
  chat: {
    chat_stream_errors: ['rate<0.20'], // 上游 LLM 限流允许少量失败
    chat_stream_total_ms: ['p(90)<60000'], // 单条流（检索+生成+门控）p90 < 60s
    chat_first_event_ms: ['p(90)<15000'], // 首事件（检索+排队）p90 < 15s
  },
};

export const options = {
  scenarios: MODE === 'infra' ? { infra: SCENARIOS.infra } : { chat: SCENARIOS.chat },
  thresholds: THRESHOLDS[MODE] || THRESHOLDS.chat,
  discardResponseBodies: false, // chat 模式需要解析 SSE 响应体
  setupTimeout: '30s',
};

// ── setup：注册（或登录）压测专用账号，返回 token ──
export function setup() {
  const creds = {
    username: `k6_loadtest_${Date.now()}`,
    email: `k6_loadtest_${Date.now()}@loadtest.local`,
    password: 'K6loadtest#2026',
  };
  const headers = { 'Content-Type': 'application/json' };

  let res = http.post(`${BASE_URL}/api/auth/register`, JSON.stringify(creds), { headers });
  if (res.status !== 200) {
    // 已存在（多次运行）则登录
    res = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify(creds), { headers });
  }
  check(res, { 'auth 获取 token 成功': (r) => r.status === 200 });
  const token = res.status === 200 ? res.json('access_token') : '';
  if (!token) {
    throw new Error(`setup 拿不到 token: ${res.status} ${res.body}`);
  }
  return { token };
}

// ── 场景 1：基础设施基线 ──
export function infraScenario() {
  const res = http.get(`${BASE_URL}/health`);
  check(res, { 'health 200': (r) => r.status === 200 });
  sleep(0.1);
}

// ── 场景 2：SSE 流式问答（完整消费流，事后解析响应体）──
export function chatScenario(data) {
  const res = http.post(
    `${BASE_URL}/api/chat/stream`,
    JSON.stringify({ message: CHAT_QUESTION }),
    {
      headers: {
        Authorization: `Bearer ${data.token}`,
        'Content-Type': 'application/json',
      },
      timeout: '180s', // SSE 长响应：默认 60s 不够
    }
  );

  // waiting = 首个响应字节 ≈ 首 SSE 事件（session_id）到达时间
  chatFirstEventMs.add(res.timings.waiting);
  // duration = 整条流消费完毕的总时长
  chatStreamTotalMs.add(res.timings.duration);

  const body = res.body || '';
  const streamError = body.includes('"error"'); // 流内结构化错误事件（HTTP 仍 200）
  const sawDone = body.includes('[DONE]'); // 正常收尾标记
  const okStatus = check(res, { 'SSE HTTP 200': (r) => r.status === 200 });

  chatStreamErrors.add(!okStatus || streamError || !sawDone);

  // 提取 usage 事件的总 token（取最后一次匹配，即本请求全部 LLM 调用归集值）
  const match = body.match(/"total_tokens":\s*(\d+)/g);
  if (match) {
    const last = match[match.length - 1].match(/\d+/);
    if (last) chatTotalTokens.add(Number(last[0]));
  }

  sleep(1);
}
