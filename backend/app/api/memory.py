"""长期记忆管理 API（14.3 用户主权模式）

用户在前端手动维护跨会话背景资料（非 agent 自动抽取）：
- 法律场景 agent 记错事实的代价高于记不住——授权与准确性都由用户背书
- 存储走 LangGraph PostgresStore（与 checkpoint 同一套 PG），namespace 按 user_id 分区
- 注入在请求时现查现用（workflow._load_user_memories），不进 checkpoint
"""
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.dependencies import get_current_user
from app.models.user import User
from app.llm.checkpoint import get_store
from app.config import settings

logger = logging.getLogger("app.api.memory")

router = APIRouter()

# Store namespace 前缀：("memories", user_id) 两级分区，天然按用户隔离
_NS = "memories"


def _ns(user: User) -> tuple:
    return (_NS, str(user.id))


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=settings.USER_MEMORY_MAX_CHARS,
                         description="背景描述，如'本人在深圳一家互联网公司工作，月工资1万'")
    tag: str = Field(default="背景", max_length=20, description="分类标签：背景/偏好/案件")


@router.get("", summary="列出我的长期记忆")
async def list_memories(user: User = Depends(get_current_user)):
    items = await get_store().asearch(_ns(user), limit=settings.USER_MEMORY_MAX_COUNT)
    return {
        "items": [
            {
                "key": item.key,
                "content": item.value.get("content", ""),
                "tag": item.value.get("tag", "背景"),
                "created_at": item.value.get("created_at", ""),
            }
            for item in items
        ]
    }


@router.post("", status_code=status.HTTP_201_CREATED, summary="添加一条长期记忆")
async def add_memory(body: MemoryCreate, user: User = Depends(get_current_user)):
    store = get_store()
    # 条数上限：先查后写（Store 无原子 count，用户手动添加场景下竞争窗口可忽略）
    existing = await store.asearch(_ns(user), limit=settings.USER_MEMORY_MAX_COUNT)
    if len(existing) >= settings.USER_MEMORY_MAX_COUNT:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"最多保留 {settings.USER_MEMORY_MAX_COUNT} 条背景，请先删除部分条目",
        )
    key = uuid.uuid4().hex
    await store.aput(_ns(user), key, {
        "content": body.content.strip(),
        "tag": body.tag,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"key": key}


@router.delete("/{key}", summary="删除一条长期记忆（用户主权：删了就真没了）")
async def delete_memory(key: str, user: User = Depends(get_current_user)):
    await get_store().adelete(_ns(user), key)
    return {"ok": True}
