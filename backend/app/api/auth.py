from fastapi import APIRouter
from pydantic import BaseModel
from datetime import timedelta
from tortoise.exceptions import IntegrityError

from app.models.user import User
from app.utils.security import verify_password, get_password_hash, create_access_token
from app.config import settings
from app.exceptions import AuthError, ErrorCode

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    nickname: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    nickname: str = ""


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest):
    if await User.filter(username=req.username).exists():
        raise AuthError(ErrorCode.AUTH_USERNAME_TAKEN)
    if await User.filter(email=req.email).exists():
        raise AuthError(ErrorCode.AUTH_EMAIL_TAKEN)

    nickname = req.nickname or req.username
    try:
        user = await User.create(
            username=req.username,
            email=req.email,
            hashed_password=get_password_hash(req.password),
            nickname=nickname,
        )
    except IntegrityError:
        # 并发竞态兜底：exists 检查与 create 之间另一请求可能已插入同名/同邮箱，
        # 唯一约束是最终防线，捕获后转成友好的 409 而非 500
        if await User.filter(username=req.username).exists():
            raise AuthError(ErrorCode.AUTH_USERNAME_TAKEN) from None
        raise AuthError(ErrorCode.AUTH_EMAIL_TAKEN) from None

    token = create_access_token({"sub": str(user.id)},
                                timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    return TokenResponse(access_token=token, username=user.username, nickname=user.nickname)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    user = await User.get_or_none(username=req.username)
    if not user or not verify_password(req.password, user.hashed_password):
        raise AuthError(ErrorCode.AUTH_BAD_CREDENTIALS)
    token = create_access_token({"sub": str(user.id)},
                                timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    return TokenResponse(access_token=token, username=user.username, nickname=user.nickname)
