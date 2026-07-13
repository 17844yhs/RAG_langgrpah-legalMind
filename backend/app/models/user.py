"""用户数据模型"""
from tortoise import fields
from tortoise.models import Model

class User(Model):
    """用户模型"""
    id = fields.UUIDField(pk=True)
    username = fields.CharField(max_length=100,unique=True,description="用户名")
    email = fields.CharField(max_length=200, unique=True,description="邮箱")
    hashed_password = fields.CharField(max_length=255,description="密码")
    is_active = fields.BooleanField(default=True,description="是否激活")
    nickname = fields.CharField(max_length=100, null=True,description="昵称")
    created_at = fields.DatetimeField(auto_now_add=True,description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True,description="更新时间")

    class Meta:
        table = "users"