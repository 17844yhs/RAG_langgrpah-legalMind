"""聊天数据模型"""
from tortoise import fields
from tortoise.models import Model


class ChatSession(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User",related_name="chat_sessions",on_delete=fields.CASCADE)
    session_id = fields.CharField(max_length=100, unique=True, description="会话ID")
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")

    class Meta:
        table = "chat_sessions"

class ChatMessageRecord(Model):
    id = fields.IntField(pk=True, description="主键ID")
    chat_session = fields.ForeignKeyField("models.ChatSession", related_name="messages", on_delete=fields.CASCADE, description="关联聊天会话")
    role = fields.CharField(max_length=20, description="消息角色（user/assistant）")
    content = fields.TextField(description="消息内容")
    meta = fields.JSONField(null=True, description="回答元数据（summary/risk_level/applicable_laws，仅 assistant 消息）")
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")

    class Meta:
        table = "chat_messages"
        # 历史消息查询：WHERE chat_session_id = ? ORDER BY created_at
        # PostgreSQL 的 FK 列不自动建索引，复合索引让该查询走 index scan 免排序
        indexes = [("chat_session_id", "created_at")]
