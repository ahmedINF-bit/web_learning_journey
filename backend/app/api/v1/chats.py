from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.chat import Chat, Message
from app.models.user import User
from app.models.user_memory import UserMemory
from app.schemas.chat import (
    ChatCreate,
    ChatUpdate,
    ChatResponse,
    ChatDetailResponse,
    MessageCreate,
    MessageResponse,
)
from app.services.ai_service import AIService, AIServiceUnavailable
from app.services.memory_service import MemoryService
from app.services.subscription_service import enforce_ai_quota


router = APIRouter(prefix="/chats", tags=["Chats"])


# ============================================================
# LIST CHATS
# ============================================================

@router.get("", response_model=list[ChatResponse])
async def list_chats(
    folder_id: Optional[int] = None,
    search: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Chat).where(Chat.user_id == user.id)

    if folder_id is not None:
        query = query.where(Chat.folder_id == folder_id)

    if search:
        query = query.where(
            Chat.title.ilike(f"%{search}%")
        )

    query = query.order_by(
        desc(Chat.is_pinned),
        desc(Chat.updated_at),
    )

    result = await db.execute(query)
    chats = result.scalars().all()

    response = []

    for chat in chats:
        msg_count = await db.execute(
            select(func.count(Message.id)).where(
                Message.chat_id == chat.id
            )
        )

        count = msg_count.scalar() or 0

        chat_response = ChatResponse.model_validate(chat)
        chat_response.message_count = count

        response.append(chat_response)

    return response


# ============================================================
# CREATE CHAT
# ============================================================

@router.post("", response_model=ChatDetailResponse)
async def create_chat(
    data: ChatCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    chat = Chat(
        user_id=user.id,
        title=data.title,
        folder_id=data.folder_id,
    )

    db.add(chat)

    await db.commit()
    await db.refresh(chat)

    return ChatDetailResponse(
        id=chat.id,
        title=chat.title,
        folder_id=chat.folder_id,
        is_pinned=chat.is_pinned,
        messages=[],
        created_at=chat.created_at,
        updated_at=chat.updated_at,
    )


# ============================================================
# GET CHAT
# ============================================================

@router.get("/{chat_id}", response_model=ChatDetailResponse)
async def get_chat(
    chat_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Chat)
        .options(selectinload(Chat.messages))
        .where(
            Chat.id == chat_id,
            Chat.user_id == user.id,
        )
    )

    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    messages = sorted(
        chat.messages,
        key=lambda message: message.created_at,
    )

    return ChatDetailResponse(
        id=chat.id,
        title=chat.title,
        folder_id=chat.folder_id,
        is_pinned=chat.is_pinned,
        messages=[
            MessageResponse.model_validate(message)
            for message in messages
        ],
        created_at=chat.created_at,
        updated_at=chat.updated_at,
    )


# ============================================================
# UPDATE CHAT
# ============================================================

@router.put("/{chat_id}", response_model=ChatResponse)
async def update_chat(
    chat_id: int,
    data: ChatUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.user_id == user.id,
        )
    )

    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    if data.title is not None:
        chat.title = data.title

    if data.folder_id is not None:
        chat.folder_id = data.folder_id

    if data.is_pinned is not None:
        chat.is_pinned = data.is_pinned

    await db.commit()
    await db.refresh(chat)

    msg_count = (
        await db.execute(
            select(func.count(Message.id)).where(
                Message.chat_id == chat.id
            )
        )
    ).scalar() or 0

    response = ChatResponse.model_validate(chat)
    response.message_count = msg_count

    return response


# ============================================================
# DELETE CHAT
# ============================================================

@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.user_id == user.id,
        )
    )

    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    await db.delete(chat)
    await db.commit()

    return {
        "message": "Chat deleted"
    }


# ============================================================
# SEND MESSAGE
# ============================================================

@router.post(
    "/{chat_id}/messages",
    response_model=MessageResponse,
)
async def send_message(
    chat_id: int,
    data: MessageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _quota: None = Depends(enforce_ai_quota),
):
    # --------------------------------------------------------
    # 1. التحقق من وجود المحادثة
    # --------------------------------------------------------

    result = await db.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.user_id == user.id,
        )
    )

    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    # --------------------------------------------------------
    # 2. حفظ رسالة المستخدم
    # --------------------------------------------------------

    user_message = Message(
        chat_id=chat.id,
        role="user",
        content=data.content,
    )

    db.add(user_message)

    await db.flush()

    # ========================================================
    # 3. MEMORY SYSTEM
    # ========================================================

    memory_service = MemoryService(
        db=db,
        user_id=user.id,
    )

    await memory_service.process_message(
        data.content
    )
    # ========================================================
    # 4. جلب تاريخ المحادثة
    # ========================================================

    history_result = await db.execute(
        select(Message)
        .where(
            Message.chat_id == chat.id,
            Message.id != user_message.id,
        )
        .order_by(
            Message.created_at.asc(),
            Message.id.asc(),
        )
        .limit(20)
    )

    history_messages = history_result.scalars().all()

    # ========================================================
    # 5. تحويل History إلى صيغة Gemini
    # ========================================================

    history = []

    for message in history_messages:
        if message.role == "user":
            history.append(
                {
                    "role": "user",
                    "content": message.content,
                }
            )

        elif message.role == "assistant":
            history.append(
                {
                    "role": "model",
                    "content": message.content,
                }
            )

    # الرسالة الحالية
    history.append(
        {
            "role": "user",
            "content": data.content,
        }
    )

    # ========================================================
    # 6. جلب CURRENT MEMORIES
    # ========================================================

    memory_result = await db.execute(
        select(UserMemory)
        .where(UserMemory.user_id == user.id)
        .order_by(UserMemory.id)
    )

    memories = memory_result.scalars().all()

    memory_context = [
        memory.content
        for memory in memories
    ]

    # ========================================================
    # 7. إنشاء SYSTEM MEMORY PROMPT
    # ========================================================

    memory_system_message = None

    if memory_context:
        memory_text = "\n".join(
            f"- {memory}"
            for memory in memory_context
        )

        memory_system_message = (
            "You are an AI assistant with access to the "
            "user's current stored memories.\n\n"

            "IMPORTANT MEMORY RULES:\n"

            "1. The stored memories below represent the "
            "user's CURRENT known personal information.\n"

            "2. For direct questions about the user's personal "
            "information, ALWAYS use the current stored memories "
            "as the authoritative source.\n"

            "3. Older messages in the conversation history may "
            "contain outdated personal information. Treat them "
            "as historical context only.\n"

            "4. If an old message conflicts with a current memory, "
            "IGNORE the old value for the purpose of answering "
            "the user's current personal-information question.\n"

            "5. Do not mention old conflicting information unless "
            "the user explicitly asks about the history or the change.\n"

            "6. Do not list all user memories unless the user asks "
            "for a profile, summary, or similar request.\n"

            "7. Answer direct personal-information questions "
            "directly and concisely.\n"

            "8. Do not invent personal information that is not "
            "present in the memories or current conversation.\n"

            "9. Do not claim that you personally saved, updated, "
            "deleted, or modified a memory.\n"

            "10. The application's memory system is responsible "
            "for saving and updating memories.\n"

            "11. For direct personal-information questions, "
            "return the current value from CURRENT USER MEMORIES "
            "without discussing outdated history.\n\n"

            "12. Never guess or invent the user's name. "
            "If the user's name is not explicitly confirmed by "
            "the current conversation or reliable stored information, "
            "greet the user without using a personal name.\n\n"

            "CURRENT USER MEMORIES:\n"
            f"{memory_text}"
        )

    else:
        memory_system_message = (
            "You are Talaba AI, a helpful AI assistant.\n\n"
            "Never guess or invent the user's name. "
            "Only use a name when it is explicitly provided "
            "in the current conversation or supplied by "
            "trusted application data. "
            "If the name is unknown, greet the user without "
            "using a personal name.\n"
            "Do not invent personal information.\n"
        )
    # ========================================================
    # 8. إضافة SYSTEM MEMORY إلى History
    # ========================================================

    if memory_system_message:
        history.insert(
            0,
            {
                "role": "system",
                "content": memory_system_message,
            },
        )

    # ========================================================
    # 9. DEBUG
    # ========================================================

    if settings.DEBUG:
        print("\n========== MEMORIES ==========")

        for memory in memory_context:
            print(f"MEMORY: {memory}")

        print("================================\n")

        print("\n========== GEMINI HISTORY ==========")

        for msg in history:
            print(
                f"{msg['role']}: {msg['content']}"
            )

        print("====================================\n")

    # ========================================================
    # 10. التحقق من History
    # ========================================================

    if not history:
        raise ValueError(
            "Conversation history is empty."
        )

    # الرسالة الأخيرة يجب أن تكون user
    # والـ system موجودة في البداية فقط
    if history[-1]["role"] != "user":
        raise ValueError(
            "Conversation history must end with user, "
            f"got: {history[-1]['role']}"
        )

    # ========================================================
    # 11. تحديد الموديل
    # ========================================================

    model_name = settings.GEMINI_MODEL

    # ========================================================
    # 12. إنشاء AI Service
    # ========================================================

    ai = AIService(
        api_key=settings.GEMINI_API_KEY
    )

    # ========================================================
    # 13. إرسال History إلى Gemini
    # ========================================================

    try:
        ai_response = await ai.chat(
            messages=history,
            model=model_name,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
        )

    except AIServiceUnavailable as e:
        if e.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail=(
                    "The AI service is rate-limited or has reached "
                    "its current quota. Please try again later."
                ),
                headers={"Retry-After": "10"},
            ) from e

        raise HTTPException(
            status_code=503,
            detail=(
                "The AI service is temporarily unavailable. "
                "Please try again shortly."
            ),
            headers={"Retry-After": "10"},
        ) from e

    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(
            "AI chat request failed"
        )
        raise HTTPException(
            status_code=502,
            detail="The AI service request failed. Please try again.",
        ) from e

    # ========================================================
    # 14. حفظ رد AI
    # ========================================================

    assistant_message = Message(
        chat_id=chat.id,
        role="assistant",
        content=ai_response,
        model=model_name,
        tokens_used=len(ai_response.split()) * 2,
    )

    db.add(assistant_message)

    # ========================================================
    # 15. تغيير عنوان المحادثة
    # ========================================================

    if chat.title == "New Chat":
        chat.title = (
            data.content[:80]
            + (
                "..."
                if len(data.content) > 80
                else ""
            )
        )

    # ========================================================
    # 16. حفظ كل التغييرات
    # ========================================================

    await db.commit()

    await db.refresh(assistant_message)

    # ========================================================
    # 17. إرجاع الرد
    # ========================================================

    return MessageResponse.model_validate(
        assistant_message
    )
