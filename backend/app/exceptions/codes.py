"""统一错误码注册表

规范：{模块}_{三位序号}。
- code 给程序看：前端据此做逻辑分支（如 AUTH_001 跳登录页），永不改变
- detail 给人看：默认文案可随时调整，甚至做多语言
- HTTP 状态码在此处"一处定义"，业务代码不再关心状态码
"""

from enum import Enum


class ErrorCode(str, Enum):
    # ── 系统（SYS）──
    SYS_INTERNAL = "SYS_001"      # 未捕获异常兜底，对外只回 traceId
    SYS_VALIDATION = "SYS_002"    # 请求参数校验失败（Pydantic）

    # ── 认证（AUTH）──
    AUTH_NOT_LOGGED_IN = "AUTH_001"
    AUTH_INVALID_TOKEN = "AUTH_002"
    AUTH_USER_NOT_FOUND = "AUTH_003"
    AUTH_BAD_CREDENTIALS = "AUTH_004"
    AUTH_USERNAME_TAKEN = "AUTH_005"
    AUTH_EMAIL_TAKEN = "AUTH_006"

    # ── 聊天（CHAT）──
    CHAT_SESSION_NOT_FOUND = "CHAT_001"

    # ── 案例（CASE）──
    CASE_NOT_FOUND = "CASE_001"

    # ── 检索（RAG）──
    RAG_RETRIEVAL_FAILED = "RAG_001"


# 错误码 → (HTTP 状态码, 默认 detail 文案)
_CODE_META: dict[ErrorCode, tuple[int, str]] = {
    ErrorCode.SYS_INTERNAL: (500, "服务器内部错误"),
    ErrorCode.SYS_VALIDATION: (400, "请求参数错误"),
    ErrorCode.AUTH_NOT_LOGGED_IN: (401, "未登录"),
    ErrorCode.AUTH_INVALID_TOKEN: (401, "无效的认证凭证"),
    ErrorCode.AUTH_USER_NOT_FOUND: (401, "用户不存在"),
    ErrorCode.AUTH_BAD_CREDENTIALS: (401, "用户名或密码错误"),
    ErrorCode.AUTH_USERNAME_TAKEN: (400, "用户名已注册"),
    ErrorCode.AUTH_EMAIL_TAKEN: (400, "邮箱已注册"),
    ErrorCode.CHAT_SESSION_NOT_FOUND: (404, "会话不存在"),
    ErrorCode.CASE_NOT_FOUND: (404, "没有找到这个案例"),
    ErrorCode.RAG_RETRIEVAL_FAILED: (500, "检索服务暂时不可用"),
}
