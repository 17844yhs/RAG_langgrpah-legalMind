"""图形验证码：生成 + Redis 一次性存取（防登录/注册接口爆破）

安全设计（每条都是硬约束）：
- 一次性消费：verify 用 GETDEL，取到即删（无论对错）——同 id 重放/复用直接失败
- TTL 5 分钟：EXPIRE 兜底，过期即失效
- 大小写不敏感：用户友好惯例，比对前统一 upper()
- 易混淆字符剔除：字符表去掉 O/0/I/1/L，避免用户分不清输错
- fail-closed：Redis 不可达时校验直接异常 → 500 兜底，宁可登录不可用也不放行爆破
"""
import base64
import io
import secrets
import string

from captcha.image import ImageCaptcha

# 验证码参数（自包含安全特性，不做运维可调项）
CODE_LENGTH = 4
CAPTCHA_TTL_SECONDS = 300
_ALPHABET = "".join(
    c for c in string.ascii_uppercase + string.digits if c not in "O0I1L"
)

_state = {"client": None}


def _get_client():
    """懒创建 Redis 客户端（与 redis_cache 同款 RESP2 兼容配置）"""
    if _state["client"] is None:
        import redis.asyncio as aioredis

        from app.config import settings
        _state["client"] = aioredis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
            protocol=2,
        )
    return _state["client"]


def generate_captcha() -> tuple[str, str, str]:
    """生成一题：返回 (captcha_id, 标准答案 code, PNG base64 data URL)"""
    code = "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LENGTH))
    buf = io.BytesIO()
    ImageCaptcha(width=132, height=44).write(code, buf, format="PNG")
    captcha_id = secrets.token_hex(16)
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return captcha_id, code, data_url


async def save_captcha(captcha_id: str, code: str) -> None:
    """存标准答案，TTL 到期自动清除（SET+EX 自 2.6.12 支持，比弃用的 setex 更老兼容）"""
    await _get_client().set(
        f"captcha:{captcha_id}", code, ex=CAPTCHA_TTL_SECONDS
    )


# 原子 getdel：GETDEL 命令 Redis 6.2 才有，老服务端（如 Windows Redis 3.0）不认；
# Lua 脚本（EVAL 自 2.6 起支持）等价实现，并消除"先读后删"的竞态窗口
_GETDEL_LUA = (
    "local v = redis.call('GET', KEYS[1]) "
    "if v then redis.call('DEL', KEYS[1]) end "
    "return v"
)


async def verify_captcha(captcha_id: str, user_input: str) -> bool:
    """校验并一次性消费：原子 get+del，错码/重放/过期统一 False"""
    if not captcha_id or not user_input:
        return False
    code = await _get_client().eval(_GETDEL_LUA, 1, f"captcha:{captcha_id}")
    if code is None:
        return False
    return user_input.strip().upper() == code.decode().upper()
