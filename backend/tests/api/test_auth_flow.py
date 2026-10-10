"""API 集成测试：认证链路（注册/登录/重复注册/错误密码/验证码）— 黑盒

真库（legal_db_test）真 ORM 真 Redis，验证认证端到端行为与错误码。
验证码答案从 Redis 读出（等价于人工识图），走的是真实 /captcha → verify 链路。
"""
import uuid


def _creds():
    h = uuid.uuid4().hex[:8]
    return {"username": f"user_{h}", "email": f"{h}@test.com", "password": "Passw0rd!"}


async def test_register_login_flow(client, get_captcha):
    creds = _creds()

    resp = await client.post("/api/v1/auth/register",
                             json={**creds, **(await get_captcha(client))})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["username"] == creds["username"]

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": creds["username"], "password": creds["password"],
              **(await get_captcha(client))})
    assert login.status_code == 200
    assert login.json()["access_token"]


async def test_register_duplicate_username(client, get_captcha):
    creds = _creds()
    first = await client.post("/api/v1/auth/register",
                              json={**creds, **(await get_captcha(client))})
    assert first.status_code == 200

    # 第二次注册也要领新题（每次提交独立消费一题）
    dup = await client.post("/api/v1/auth/register",
                            json={**creds, **(await get_captcha(client))})
    assert dup.status_code == 400
    body = dup.json()
    assert body["code"] == "AUTH_005"          # AUTH_USERNAME_TAKEN
    assert body["detail"] == "用户名已注册"
    assert body["traceId"]


async def test_login_wrong_password(client, get_captcha):
    creds = _creds()
    await client.post("/api/v1/auth/register",
                      json={**creds, **(await get_captcha(client))})

    bad = await client.post(
        "/api/v1/auth/login",
        json={"username": creds["username"], "password": "wrong!",
              **(await get_captcha(client))})
    assert bad.status_code == 401
    assert bad.json()["code"] == "AUTH_004"    # AUTH_BAD_CREDENTIALS


async def test_register_wrong_captcha_rejected(client, get_captcha):
    """错码 → 400 AUTH_007；且错码也被一次性消费（防爆破枚举）"""
    creds = _creds()
    pair = await get_captcha(client)
    resp = await client.post("/api/v1/auth/register",
                             json={**creds, **pair, "captcha_code": "XXXX"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "AUTH_007"          # AUTH_CAPTCHA_INVALID
    assert "验证码" in body["detail"]


async def test_captcha_replay_rejected(client, get_captcha):
    """同题二次提交（重放）→ AUTH_007——GETDEL 一次性消费语义"""
    creds = _creds()
    pair = await get_captcha(client)

    first = await client.post("/api/v1/auth/register", json={**creds, **pair})
    assert first.status_code == 200

    replay = await client.post("/api/v1/auth/register",
                               json={**_creds(), **pair})
    assert replay.status_code == 400
    assert replay.json()["code"] == "AUTH_007"


async def test_captcha_missing_params_rejected(client, get_captcha):
    """缺验证码字段 → 校验处理器统一契约：400 SYS_002，根本到不了业务逻辑"""
    resp = await client.post("/api/v1/auth/register", json=_creds())
    assert resp.status_code == 400
    assert resp.json()["code"] == "SYS_002"


async def test_captcha_endpoint_returns_image(client, get_captcha):
    """/captcha 契约：data URL PNG + captcha_id（此测试不消费该题）"""
    resp = await client.get("/api/v1/auth/captcha")
    assert resp.status_code == 200
    body = resp.json()
    assert body["captcha_id"]
    assert body["image"].startswith("data:image/png;base64,")


async def test_protected_endpoint_without_token(client):
    """无 Bearer token → 401 AUTH_001（Problem Details 格式）"""
    resp = await client.post("/api/v1/chat/stream", json={"message": "你好"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "AUTH_001"
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_protected_endpoint_with_garbage_token(client):
    """伪造 token → 401 AUTH_002（JWTError 分支）"""
    resp = await client.post("/api/v1/chat/stream",
                             headers={"Authorization": "Bearer not.a.jwt"},
                             json={"message": "你好"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_002"
