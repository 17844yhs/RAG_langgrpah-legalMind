"""安全工具"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.config import settings

_PBKDF2_ITERATIONS = 100_000


def get_password_hash(password: str) -> str:
    """生成密码哈希：随机盐 + PBKDF2-SHA256"""
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS
    ).hex()
    return f"{salt}${hashed}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码：拆出盐值，重新计算哈希，比对

    用 secrets.compare_digest 恒时比较，防止逐字节侧信道；
    哈希串格式非法（盐/哈希缺一半）一律按验证失败处理。
    """
    try:
        salt, stored_hash = hashed_password.split("$", 1)
    except ValueError:
        return False
    computed = hashlib.pbkdf2_hmac(
        "sha256", plain_password.encode(), salt.encode(), _PBKDF2_ITERATIONS
    ).hex()
    return secrets.compare_digest(computed, stored_hash)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """签发 JWT Token"""
    to_encode = data.copy()
    # 默认 1440 分钟 = 24 小时
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=1440))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
