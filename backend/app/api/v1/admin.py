from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.chat import Chat, Message
from app.models.file import File
from app.schemas.settings import AdminStats

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats", response_model=AdminStats)
async def get_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin:
        total_users = 1
        total_chats = (await db.execute(select(func.count(Chat.id)))).scalar() or 0
        total_messages = (await db.execute(select(func.count(Message.id)))).scalar() or 0
        total_files = (await db.execute(select(func.count(File.id)))).scalar() or 0
    else:
        total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
        total_chats = (await db.execute(select(func.count(Chat.id)))).scalar() or 0
        total_messages = (await db.execute(select(func.count(Message.id)))).scalar() or 0
        total_files = (await db.execute(select(func.count(File.id)))).scalar() or 0

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    active_users = (await db.execute(
        select(func.count(func.distinct(Message.id))).join(Chat).where(Message.created_at >= today)
    )).scalar() or 0
    messages_today = (await db.execute(
        select(func.count(Message.id)).where(Message.created_at >= today)
    )).scalar() or 0

    return AdminStats(
        total_users=total_users,
        total_chats=total_chats,
        total_messages=total_messages,
        total_files=total_files,
        active_users_today=active_users,
        messages_today=messages_today,
    )


@router.get("/users")
async def list_users(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin access required")
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [
        {
            "id": u.id, "username": u.username, "email": u.email,
            "is_active": u.is_active, "is_admin": u.is_admin,
            "created_at": str(u.created_at),
        }
        for u in users
    ]
