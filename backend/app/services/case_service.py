"""案例服务"""
from typing import Optional, Dict, List

from tortoise.queryset import Q

from app.models.case import Case


class CaseService:
    """案例服务"""
    async def get_by_id(self, case_id: str) -> Optional[Dict]:
        case = await Case.get_or_none(id=case_id)
        if case:
            return case.to_dict()
        return None

    async def search(self, query: str, case_type: Optional[str] = None,
                     court: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """
        根据关键词和筛选条件搜索案例列表。

        Args:
            query (str): 搜索关键词，对标题/摘要/全文做模糊匹配。
            case_type (Optional[str]): 案件类型（如"民事"、"刑事"等），可选。
            court (Optional[str]): 法院名称，可选。
            limit (int): 返回结果的最大数量，默认为 10。

        Returns:
            List[Dict]: 符合条件的案例列表，每个案例以字典形式表示。
        """
        qs = Case.all()
        if query:
            # 模糊匹配（等值查询对全文内容永远命中不了；三个字段任一命中即可）
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(summary__icontains=query)
                | Q(content__icontains=query)
            )
        if case_type:
            qs = qs.filter(case_type=case_type)
        if court:
            qs = qs.filter(court__icontains=court)
        cases = await qs.limit(limit)
        return [case.to_dict() for case in cases]