"""API 集成测试：认证链路（注册/登录/重复注册/错误密码）— 黑盒

真库（legal_db_test）真 ORM，验证的是认证端到端行为与错误码。
"""
import uuid


def _creds():
    h = uuid.uuid4().hex[:8]
    return {"username": f"user_{h}", "email": f"{h}@test.com", "password": "Passw0rd!"}


async def test_register_login_flow(client):
    creds = _creds()

    resp = await client.post("/api/auth/register", json=creds)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["username"] == creds["username"]

    login = await client.post("/api/auth/login",
                              json={"username": creds["username"],
                                    "password": creds["password"]})
    assert login.status_code == 200
    assert login.json()["access_token"]


async def test_register_duplicate_username(client):
    creds = _creds()
    first = await client.post("/api/auth/register", json=creds)
    assert first.status_code == 200

    dup = await client.post("/api/auth/register", json=creds)
    assert dup.status_code == 400
    body = dup.json()
    assert body["code"] == "AUTH_005"          # AUTH_USERNAME_TAKEN
    assert body["detail"] == "用户名已注册"
    assert body["traceId"]


async def test_login_wrong_password(client):
    creds = _creds()
    await client.post("/api/auth/register", json=creds)

    bad = await client.post("/api/auth/login",
                            json={"username": creds["username"], "password": "wrong!"})
    assert bad.status_code == 401
    assert bad.json()["code"] == "AUTH_004"    # AUTH_BAD_CREDENTIALS


async def test_protected_endpoint_without_token(client):
    """无 Bearer token → 401 AUTH_001（Problem Details 格式）"""
    resp = await client.post("/api/chat/stream", json={"message": "你好"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "AUTH_001"
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_protected_endpoint_with_garbage_token(client):
    """伪造 token → 401 AUTH_002（JWTError 分支）"""
    resp = await client.post("/api/chat/stream",
                             headers={"Authorization": "Bearer not.a.jwt"},
                             json={"message": "你好"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_002"
