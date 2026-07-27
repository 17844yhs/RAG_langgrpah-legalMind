"""法律法规数据模型"""
from tortoise import fields
from tortoise.models import Model


class Law(Model):
    """法律法规模型 — 存储法条全文，供 RAG 检索和评估使用"""
    id = fields.CharField(max_length=50, pk=True, description="法条ID，如 law_001")
    title = fields.CharField(max_length=200, description="法条标题")
    content = fields.TextField(description="法条全文")
    source = fields.CharField(max_length=200, null=True, description="数据来源")
    category = fields.CharField(max_length=50, null=True, description="法律类别")
    keywords = fields.JSONField(null=True, description="关键词列表")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "laws"

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "category": self.category,
            "keywords": self.keywords,
        }
