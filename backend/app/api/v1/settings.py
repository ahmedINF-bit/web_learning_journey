from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.settings import UserSettings
from app.models.subscription import Subscription
from app.schemas.settings import SettingsUpdate, SettingsResponse, SubscriptionResponse, APIKeyUpdate
from app.services.subscription_service import get_plan_daily_limit

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(user_id=user.id)
        db.add(settings)
        await db.flush()
    return SettingsResponse.model_validate(settings)


@router.put("", response_model=SettingsResponse)
async def update_settings(
    data: SettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(user_id=user.id)
        db.add(settings)

    if data.theme is not None:
        settings.theme = data.theme
    if data.language is not None:
        settings.language = data.language
    if data.temperature is not None:
        settings.temperature = data.temperature
    if data.max_tokens is not None:
        settings.max_tokens = data.max_tokens
    if data.system_prompt is not None:
        settings.system_prompt = data.system_prompt
    if data.notifications_enabled is not None:
        settings.notifications_enabled = data.notifications_enabled

    await db.flush()
    return SettingsResponse.model_validate(settings)


@router.put("/api-key")
async def update_api_key(data: APIKeyUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user.openai_api_key = data.api_key
    await db.flush()
    return {"message": "API key updated"}


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    sub = result.scalar_one_or_none()
    if not sub:
        sub = Subscription(user_id=user.id)
        db.add(sub)
        await db.flush()
    response = SubscriptionResponse.model_validate(sub)
    response.messages_limit = get_plan_daily_limit(sub.plan)
    return response


@router.delete("/account")
async def delete_account(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.delete(user)
    return {"message": "Account deleted"}


@router.post("/export")
async def export_data(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.chat import Chat, Message
    from app.models.note import Note

    chats_r = await db.execute(select(Chat).where(Chat.user_id == user.id))
    notes_r = await db.execute(select(Note).where(Note.user_id == user.id))

    chats_data = []
    for chat in chats_r.scalars().all():
        msgs_r = await db.execute(select(Message).where(Message.chat_id == chat.id))
        chats_data.append({
            "title": chat.title,
            "created_at": str(chat.created_at),
            "messages": [{"role": m.role, "content": m.content} for m in msgs_r.scalars().all()],
        })

    notes_data = [{"title": n.title, "content": n.content, "created_at": str(n.created_at)} for n in notes_r.scalars().all()]

    return {"chats": chats_data, "notes": notes_data}
