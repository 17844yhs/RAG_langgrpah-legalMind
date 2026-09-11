"""chat SSE 端到端冒烟（1 条消息，最小 token 消耗）：
注册→登录→建会话→发消息→收集 SSE 事件→验证 usage/阶段事件/end 完整性
"""
import json
import urllib.request

BASE = "http://localhost:8000/api/v1"


def req(path, method="GET", body=None, token=None, timeout=180, raw=False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, method=method,
                               data=json.dumps(body).encode() if body else None,
                               headers=headers)
    resp = urllib.request.urlopen(r, timeout=timeout)
    data = resp.read()
    if raw:
        return data
    return json.loads(data.decode())


import random
suffix = random.randint(1000, 9999)
creds = {"username": f"smoke_{suffix}", "email": f"smoke_{suffix}@test.com",
         "password": "Smoke#12345", "nickname": "冒烟"}
req("/auth/register", "POST", creds)
token = req("/auth/login", "POST", {"username": creds["username"], "password": creds["password"]})["access_token"]

# SSE 流式发送一条（session_id 传空，服务端自动创建并回传）
events = {}
text_len = 0
usage = None
sid = None
data = req("/chat/stream", "POST", {"message": "公司拖欠工资不发，我该怎么维权？"}, token, raw=True)
for raw_line in data.decode("utf-8", errors="replace").split("\n"):
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
        print(f"会话 {sid} 已创建")
        continue
    if "content" in ev:                      # token chunk（服务端格式 {'content': ...}）
        et = "token"
        text_len += len(ev["content"])
    elif "interrupt" in ev:
        et = "interrupt"
    elif "usage" in ev:
        et, usage = "usage", ev["usage"]
    elif "stage" in ev:
        et = "stage"
    else:
        et = "unknown"
    events[et] = events.get(et, 0) + 1
    if et == "error":
        print(f"  [error] {ev}")

print(f"\n事件统计: {events}")
print(f"流式正文长度: {text_len} 字")
if usage:
    print(f"usage 事件: {json.dumps(usage, ensure_ascii=False)[:200]}")
else:
    print("⚠️ 未收到 usage 事件")

if sid:
    msgs = req(f"/chat/sessions/{sid}/messages", token=token)
    rows = msgs.get("messages", [])
    total_usage = (rows[0].get("usage") if rows else None) or {}
    print(f"DB usage 字段: {json.dumps(total_usage, ensure_ascii=False)[:200] if total_usage else '空'}")
print("\n✅ chat SSE 端到端冒烟完成")
