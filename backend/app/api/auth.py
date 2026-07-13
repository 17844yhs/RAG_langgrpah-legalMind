from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import timedelta
from app.models.user import User
from app.utils.security import verify_password, get_password_hash, create_access_token
from app.config import settings

router = APIRouter()

class RegisterReqeust(BaseModel):
    username:str
    email:str
    password:str
    nickname:str = ""

class LoginRequest(BaseModel):
    username:str
    password:str

class TokenResponse(BaseModel):
    access_token:str
    token_type:str='bearer'
    username:str
    nickname:str =''

@router.post("/register",response_model=TokenResponse)
async def register(req:RegisterReqeust):
    if await User.filter(username=req.username).exists():
        raise HTTPException(status_code=400,detail="用户名已注册")
    if await User.filter(email=req.email).exists():
        raise HTTPException(status_code=400,detail="邮箱已注册")

    nickname = req.nickname or req.username
    user = await User.create(
        username= req.username,
        email = req.email,
        hashed_password = get_password_hash(req.password),
        nickname = nickname
    )
    token = create_access_token({"sub":str(user.id)},timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    return TokenResponse(access_token=token,username=user.username,nickname= user.nickname)

@router.post('/login',response_model=TokenResponse)
async def login(req:LoginRequest):
    user = await User.get_or_none(username=req.username)
    if not user or not verify_password(req.password,user.hashed_password):
        raise HTTPException(status_code=401,detail="用户名或者密码错误")
    token = create_access_token({"sub":str(user.id)},timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    return TokenResponse(access_token=token,username=user.username,nickname= user.nickname)
