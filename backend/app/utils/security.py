"""安全工具"""
import hashlib
import secrets
from jose import jwt
from datetime import datetime, timedelta,timezone
from app.config import settings

def get_password_hash(password:str) -> str:
    '''
    生成密码哈西：随机盐 + PBKDF2-SHA256
    '''
    salt = secrets.token_hex(16)
    # 100000次迭代，生成哈希值
    hasded = hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),100000).hex()
    return f'{salt}${hasded}'

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码：拆出盐值，重新计算哈希，比对"""
    salt, stored_hash = hashed_password.split("$", 1)  # 拆分盐值和哈希值
    computed = hashlib.pbkdf2_hmac("sha256", plain_password.encode(), salt.encode(), 100000).hex() # 计算哈希值
    return computed == stored_hash


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """签发 JWT Token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=1440)) # 1440分钟，24小时
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256") # 使用HS256算法
