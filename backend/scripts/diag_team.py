"""层级 Agent 团队端到端验证：单领域 / 跨领域（含 HITL resume）/ 降级链
打印完整 stage 时间线，验证专家并行派发、合并逻辑与升级兜底。
"""
import json
import time
import urllib.request

BASE = "http://localhost:8000/api/v1"


def req(path, method="GET", body=None, token=None, timeout=300):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, method=method,
                               data=json.dumps(body).encode() if body else None,
                               headers=headers)
    resp = urllib.request.urlopen(r, timeout=timeout)
    return json.loads(resp.read().decode())


def consume_stream(raw_bytes, stages, stats, sid=None):
    """解析 SSE 流，返回 ('done' | 'interrupted', session_id, usage)。
    sid 跨轮保留传入：resume 流不回发 session_id，置 None 会导致下轮 resume 400"""
    usage = None
    for raw_line in raw_bytes.decode("utf-8", errors="replace").split("\n"):
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            ev = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if "session_id" in ev:
            sid = ev["session_id"]
        elif "content" in ev:
            stats["chars"] += len(ev["content"])
        elif "stage" in ev:
            s = ev["stage"]
            stages.append(f"{s['stage']:<24} [{s['status']:<7}] {s['text']}")
        elif "interrupt" in ev:
            it = ev["interrupt"]
            data = it.get("data") or it
            print(f"  ⏸ interrupt(type={data.get('type')}): {str(data.get('hint') or data.get('question'))[:60]}")
            return "interrupted", sid, usage
        elif "usage" in ev:
            usage = ev["usage"]
        elif "error" in ev:
            print(f"  [error] {ev}")
    return "done", sid, usage


def run_case(title, message, supplements):
    print(f"\n{'='*60}\n【{title}】用户输入：{message}")
    stages, stats = [], {"chars": 0}
    ok, sid, usage = consume_stream(
        _raw_stream("/chat/stream", {"message": message}), stages, stats,
    )
    round_i = 0
    while ok == "interrupted" and round_i < len(supplements):
        round_i += 1
        sup = supplements[round_i - 1]
        print(f"  ⏸ HITL 追问 → 自动补充：{sup}")
        ok, sid, usage = consume_stream(_raw_stream("/chat/resume", {
            "session_id": sid, "response": sup}), stages, stats, sid=sid)
    for s in stages:
        print(f"  {s}")
    tail = f"正文 {stats['chars']} 字"
    if usage:
        tail += f" | tokens={usage.get('total_tokens', '?')}"
    print(tail)
    return sid


def _raw_stream(path, body):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    r = urllib.request.Request(BASE + path, method="POST",
                               data=json.dumps(body).encode(), headers=headers)
    return urllib.request.urlopen(r, timeout=300).read()


import random
suffix = random.randint(1000, 9999)
creds = {"username": f"team_{suffix}", "email": f"team_{suffix}@test.com",
         "password": "Team#12345", "nickname": "团队测试"}
req("/auth/register", "POST", creds)
token = req("/auth/login", "POST", {"username": creds["username"], "password": creds["password"]})["access_token"]

# 用例 1：单领域（劳动争议）——专家 2 条 < 3 升级 ReAct，仍不足触发 HITL，跳过后生成
SKIP = "（用户没有更多补充，请基于已有检索结果直接回答）"
run_case("用例1 单领域+升级链", "公司拖欠工资不发，我该怎么维权？", [SKIP])
time.sleep(1)
# 用例 2：跨领域（婚姻 + 公司法），信息不足会触发 HITL → 两轮自动补充后应看到双专家并行
run_case("用例2 跨领域", "我要离婚，名下还有一家公司的股权，财产和股权应该怎么分？",
         ["双方都同意离婚。公司股权登记在我名下，估值约300万；另有一套婚后共同房产，价值200万。",
          "没有其他财产了，主要就是股权和房产，想知道怎么分。",
          "没有别的要补充了，请直接基于现有信息分析。"])
time.sleep(1)
# 用例 3：概念辨析（知识型）→ 领域路由应返回空 → 通用混合检索
run_case("用例3 知识型降级", "劳动合同和劳务合同有什么区别", [])

print("\n✅ 层级 Agent 团队端到端验证完成")
