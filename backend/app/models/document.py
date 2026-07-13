"""文书数据模型"""
from tortoise import fields
from tortoise.models import Model

class GeneratedDocument(Model):
    id = fields.UUIDField(pk=True, description="主键ID")
    user = fields.ForeignKeyField("models.User", related_name="documents", description="关联用户")
    title = fields.CharField(max_length=200, null=True, description="文书标题")
    document_type = fields.CharField(max_length=50, null=True, description="文书类型")
    content = fields.TextField(null=True, description="文书内容")
    params = fields.JSONField(null=True, description="生成参数")
    doc_references = fields.JSONField(null=True, description="引用文书/参考资料")
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "generated_documents"
