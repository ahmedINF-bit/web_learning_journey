from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.note import Note
from app.schemas.note import NoteCreate, NoteUpdate, NoteResponse

router = APIRouter(prefix="/notes", tags=["Notes"])


@router.get("", response_model=list[NoteResponse])
async def list_notes(
    folder_id: int | None = None,
    search: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Note).where(Note.user_id == user.id)

    if folder_id is not None:
        query = query.where(Note.folder_id == folder_id)

    if search:
        query = query.where(
            Note.title.ilike(f"%{search}%")
            | Note.content.ilike(f"%{search}%")
        )

    query = query.order_by(desc(Note.updated_at))

    result = await db.execute(query)

    return [
        NoteResponse.model_validate(note)
        for note in result.scalars().all()
    ]


@router.post("", response_model=NoteResponse)
async def create_note(
    data: NoteCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    note = Note(
        user_id=user.id,
        title=data.title,
        content=data.content,
        folder_id=data.folder_id,
    )

    db.add(note)

    await db.commit()
    await db.refresh(note)

    return NoteResponse.model_validate(note)


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Note).where(
            Note.id == note_id,
            Note.user_id == user.id,
        )
    )

    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    return NoteResponse.model_validate(note)


@router.put("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: int,
    data: NoteUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Note).where(
            Note.id == note_id,
            Note.user_id == user.id,
        )
    )

    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if data.title is not None:
        note.title = data.title

    if data.content is not None:
        note.content = data.content

    note.folder_id = data.folder_id

    await db.commit()

    # إعادة تحميل السجل من قاعدة البيانات
    result = await db.execute(
        select(Note).where(Note.id == note_id)
    )

    note = result.scalar_one()

    return NoteResponse.model_validate(note)


@router.delete("/{note_id}")
async def delete_note(
    note_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Note).where(
            Note.id == note_id,
            Note.user_id == user.id,
        )
    )

    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    await db.delete(note)
    await db.commit()

    return {"message": "Note deleted"}