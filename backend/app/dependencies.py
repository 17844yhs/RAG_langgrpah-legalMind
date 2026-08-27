from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from app.config import settings
from app.exceptions import AuthError, ErrorCode
from app.models.user import User

# 实例化Bearer认证类,auto_error=False表示如果没有提供认证信息，不会自动抛出异常，而是返回None
security = HTTPBearer(auto_error=False)

async def get_current_user(credentials:HTTPAuthorizationCredentials=Depends(security)):
    if credentials is None:
        raise AuthError(ErrorCode.AUTH_NOT_LOGGED_IN)
    # 提取Bearer后面的真实token字符串
    token = credentials.credentials
    try:
        payload = jwt.decode(token,settings.SECRET_KEY,algorithms=["HS256"])
        user_id = payload.get("sub")
        if user_id is None:
            raise AuthError(ErrorCode.AUTH_INVALID_TOKEN)
    except JWTError:
        raise AuthError(ErrorCode.AUTH_INVALID_TOKEN)
    # 根据user_id查询数据库用户，无结果返回None（TortoiseORM方法）
    user = await User.get_or_none(id=user_id)
    if not user:
        raise AuthError(ErrorCode.AUTH_USER_NOT_FOUND)

    return {"user_id":str(user.id),"username":user.username}
