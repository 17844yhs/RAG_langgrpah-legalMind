"""案例数据模型"""
from tortoise import fields
from tortoise.models import Model


class Case(Model):
    """案例模型"""
    id = fields.UUIDField(pk=True)
    title = fields.CharField(max_length=500,description="案例标题")
    case_number = fields.CharField(max_length=100, unique=True, null=True,description="案号")
    court = fields.CharField(max_length=200, null=True,description="审理法院")
    case_type = fields.CharField(max_length=50, null=True,description="案件类型")
    judgment_date = fields.DateField(null=True,description="裁判日期")
    summary = fields.TextField(null=True,description="裁判要旨/摘要")
    content = fields.TextField(null=True,description="裁判全文")
    laws = fields.JSONField(null=True,description="引用法条列表")
    case_tags = fields.JSONField(null=True,description="案例标签")
    created_at = fields.DatetimeField(auto_now_add=True,description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True,description="更新时间")

    class Meta:
        table = "cases"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "title": self.title,
            "case_number": self.case_number,
            "court": self.court,
            "case_type": self.case_type,
            "judgment_date": self.judgment_date.isoformat() if self.judgment_date else None,
            "summary": self.summary,
            "content": self.content,
            "laws": self.laws,
            "case_tags": self.case_tags,
        }
