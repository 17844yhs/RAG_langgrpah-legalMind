"""案例服务"""
from typing import Optional, Dict, List
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
            query (str): 搜索关键词（当前未使用，保留用于未来扩展）。
            case_type (Optional[str]): 案件类型（如“民事”、“刑事”等），可选。
            court (Optional[str]): 法院名称，可选。
            limit (int): 返回结果的最大数量，默认为 10。

        Returns:
            List[Dict]: 符合条件的案例列表，每个案例以字典形式表示。
        """
        qs = Case.all()
        if query:
            qs = qs.filter(content= query)
        if case_type:
            qs = qs.filter(case_type= case_type)
        if court:
            qs = qs.filter(court=court)
        cases = await qs.limit(limit)
        return [case.to_dict() for case in cases]