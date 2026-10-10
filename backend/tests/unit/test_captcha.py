"""验证码单元测试：零 Redis 依赖（fake client 注入），锁定安全契约

- 一次性消费（Lua 原子 getdel 语义）：同题重放必须拒绝
- 大小写不敏感、去空格容错
- 易混淆字符（O/0/I/1/L）不出现在题面
- 未知名/缺参/错码统一 False
"""
import base64

import pytest

from app.utils import captcha as cap


class FakeRedis:
    """只实现验证码用到的命令；存 bytes 对齐真 aioredis 契约，eval 走原子 getdel 语义"""

    def __init__(self):
        self.store = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value.encode()

    async def eval(self, script, numkeys, key):
        return self.store.pop(key, None)


@pytest.fixture
def fake_client(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cap, "_get_client", lambda: fake)
    return fake


def test_generate_captcha_shape():
    """题面契约：32 位 id / 4 位答案 / 无易混字符 / 合法 PNG data URL"""
    cid, code, image = cap.generate_captcha()
    assert len(cid) == 32
    assert len(code) == cap.CODE_LENGTH
    assert all(c not in "O0I1L" for c in code)
    assert image.startswith("data:image/png;base64,")
    base64.b64decode(image.removeprefix("data:image/png;base64,"))


async def test_verify_correct_case_insensitive(fake_client):
    """答案比对大小写不敏感（用户输入小写也算对）"""
    cid, code, _ = cap.generate_captcha()
    await cap.save_captcha(cid, code)
    assert await cap.verify_captcha(cid, code.lower()) is True


async def test_verify_strips_whitespace(fake_client):
    cid, code, _ = cap.generate_captcha()
    await cap.save_captcha(cid, code)
    assert await cap.verify_captcha(cid, f" {code} ") is True


async def test_verify_wrong_code(fake_client):
    cid, code, _ = cap.generate_captcha()
    await cap.save_captcha(cid, code)
    assert await cap.verify_captcha(cid, "XXXX") is False


async def test_verify_one_time_consumption(fake_client):
    """一次性消费：首次答对即销毁，同题重放拒绝"""
    cid, code, _ = cap.generate_captcha()
    await cap.save_captcha(cid, code)
    assert await cap.verify_captcha(cid, code) is True
    assert await cap.verify_captcha(cid, code) is False


async def test_verify_wrong_code_also_consumes(fake_client):
    """错码同样消费掉该题（防对同一题枚举多次）"""
    cid, code, _ = cap.generate_captcha()
    await cap.save_captcha(cid, code)
    assert await cap.verify_captcha(cid, "XXXX") is False
    assert await cap.verify_captcha(cid, code) is False


async def test_verify_unknown_id(fake_client):
    """过期/未知名的 id → False（TTL 到期等价场景）"""
    assert await cap.verify_captcha("no-such-id", "ABCD") is False


async def test_verify_missing_params(fake_client):
    assert await cap.verify_captcha("", "ABCD") is False
    assert await cap.verify_captcha("some-id", "") is False
    assert await cap.verify_captcha(None, None) is False
