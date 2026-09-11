"""查最新会话的 usage 落库情况"""
import asyncio
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))


async def main():
    from tortoise import Tortoise
    await Tortoise.init(
        db_url="postgres://legal_user:legal_pass@localhost:5432/legal_db",
        modules={"models": ["app.models.user", "app.models.chat"]},
    )
    from app.models.chat import ChatMessageRecord, ChatSession

    lines = []
    sessions = await ChatSession.all().order_by("-id").limit(2)
    for s in sessions:
        lines.append(f"\n会话 {s.id} (sid={s.session_id[:18]})")
        msgs = await ChatMessageRecord.filter(chat_session_id=s.id).order_by("id")
        for m in msgs:
            u = json.dumps(m.usage, ensure_ascii=False) if m.usage else "NULL"
            lines.append(f"  [{m.role}] usage={u[:140]}  content={m.content[:28]!r}")
    await Tortoise.close_connections()
    with open(os.path.join(os.path.dirname(__file__), "diag_usage.out.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


asyncio.run(main())
