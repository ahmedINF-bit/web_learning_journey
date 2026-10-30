from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.folder import Folder
from app.models.chat import Chat
from app.models.note import Note
from app.schemas.folder import FolderCreate, FolderUpdate, FolderResponse

router = APIRouter(prefix="/folders", tags=["Folders"])


@router.get("", response_model=list[FolderResponse])
async def list_folders(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Folder).where(Folder.user_id == user.id).order_by(Folder.name))
    folders = result.scalars().all()
    response = []
    for f in folders:
        chat_count = (await db.execute(select(func.count(Chat.id)).where(Chat.folder_id == f.id))).scalar() or 0
        note_count = (await db.execute(select(func.count(Note.id)).where(Note.folder_id == f.id))).scalar() or 0
        fr = FolderResponse.model_validate(f)
        fr.chat_count = chat_count
        fr.note_count = note_count
        response.append(fr)
    return response


@router.post("", response_model=FolderResponse)
async def create_folder(data: FolderCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    folder = Folder(user_id=user.id, name=data.name, color=data.color)
    db.add(folder)
    await db.flush()
    return FolderResponse.model_validate(folder)


@router.put("/{folder_id}", response_model=FolderResponse)
async def update_folder(folder_id: int, data: FolderUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Folder).where(Folder.id == folder_id, Folder.user_id == user.id))
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if data.name is not None:
        folder.name = data.name
    if data.color is not None:
        folder.color = data.color
    await db.flush()
    return FolderResponse.model_validate(folder)


@router.delete("/{folder_id}")
async def delete_folder(folder_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Folder).where(Folder.id == folder_id, Folder.user_id == user.id))
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await db.delete(folder)
    return {"message": "Folder deleted"}
