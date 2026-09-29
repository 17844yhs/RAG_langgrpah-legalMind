"""安全工具 — 密码哈希（bcrypt）+ JWT 签发

密码哈希升级记录（13.5 安全加固）：
- 新哈希统一 bcrypt（行业标准：自带随机盐 + 慢哈希，GPU 抗暴力破解强于裸 PBKDF2）
- 旧 PBKDF2 用户走兼容验证路径（按哈希格式嗅探分流），存量账号平滑过渡
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.config import settings

_PBKDF2_ITERATIONS = 100_000


def get_password_hash(password: str) -> str:
    """生成密码哈希：bcrypt（gensalt 默认 12 轮，随机盐内嵌在哈希串中）"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_pbkdf2(plain_password: str, hashed_password: str) -> bool:
    """旧版 PBKDF2-SHA256 验证（存量用户兼容路径，bcrypt 上线前的哈希格式）"""
    try:
        salt, stored_hash = hashed_password.split("$", 1)
    except ValueError:
        return False
    computed = hashlib.pbkdf2_hmac(
        "sha256", plain_password.encode(), salt.encode(), _PBKDF2_ITERATIONS
    ).hex()
    return secrets.compare_digest(computed, stored_hash)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码：按哈希格式分流

    - "$2" 开头 = bcrypt 哈希（checkpw 内部恒时比较）
    - 否则 = 旧 PBKDF2 格式（"盐$哈希"），走兼容路径（恒时比较防侧信道）
    - 格式非法一律按验证失败处理，不抛异常
    """
    if hashed_password.startswith("$2"):
        try:
            return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
        except ValueError:
            return False
    return _verify_pbkdf2(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """签发 JWT Token"""
    to_encode = data.copy()
    # 默认 1440 分钟 = 24 小时
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=1440))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
