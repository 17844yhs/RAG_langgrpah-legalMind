"""业务异常基类

分层约定：领域层（agents/rag/services）只抛领域异常，不感知 HTTP；
HTTP 状态码与响应格式由 app.exceptions.handlers 统一翻译。
"""

from app.exceptions.codes import ErrorCode, _CODE_META


class AppException(Exception):
    """所有业务异常的基类：错误码 + HTTP 状态 + 文案三合一。

    用法：
        raise AuthError(ErrorCode.AUTH_BAD_CREDENTIALS)
        raise AuthError(ErrorCode.AUTH_USERNAME_TAKEN, detail="该用户名已被占用")
    """

    def __init__(self, code: ErrorCode, detail: str | None = None, http_status: int | None = None):
        default_status, default_detail = _CODE_META[code]
        self.code = code
        self.detail = detail or default_detail
        self.http_status = http_status or default_status
        super().__init__(self.detail)


# 领域子类：调用处语义更直观，也便于按模块聚合日志/告警
class AuthError(AppException): ...
class ChatError(AppException): ...
class CaseError(AppException): ...
class RAGError(AppException): ...
