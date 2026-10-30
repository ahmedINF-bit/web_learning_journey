from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.code_project import CodeProject
from app.models.code_file import CodeFile
from app.models.folder import Folder
from app.models.user import User
from app.schemas.code_project import (
    CodeProjectCreate,
    CodeProjectResponse,
    CodeProjectUpdate,
)

router = APIRouter(prefix="/code-projects", tags=["Code Projects"])


async def validate_owned_folder(
    folder_id: int | None,
    user_id: int,
    db: AsyncSession,
) -> None:
    if folder_id is None:
        return

    result = await db.execute(
        select(Folder.id).where(
            Folder.id == folder_id,
            Folder.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found.",
        )


async def get_owned_project(
    project_id: int,
    user_id: int,
    db: AsyncSession,
) -> CodeProject:
    result = await db.execute(
        select(CodeProject).where(
            CodeProject.id == project_id,
            CodeProject.user_id == user_id,
        )
    )
    project = result.scalar_one_or_none()

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code project not found.",
        )

    return project


@router.get("", response_model=list[CodeProjectResponse])
async def list_code_projects(
    folder_id: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if folder_id is not None:
        await validate_owned_folder(folder_id, user.id, db)

    query = select(CodeProject).where(CodeProject.user_id == user.id)

    if folder_id is not None:
        query = query.where(CodeProject.folder_id == folder_id)

    result = await db.execute(query.order_by(desc(CodeProject.updated_at)))
    return [
        CodeProjectResponse.model_validate(project)
        for project in result.scalars().all()
    ]


@router.post(
    "",
    response_model=CodeProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_code_project(
    data: CodeProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await validate_owned_folder(data.folder_id, user.id, db)

    project = CodeProject(
        user_id=user.id,
        folder_id=data.folder_id,
        name=data.name,
        language=data.language,
        code=data.code,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return CodeProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=CodeProjectResponse)
async def get_code_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_owned_project(project_id, user.id, db)
    return CodeProjectResponse.model_validate(project)


@router.put("/{project_id}", response_model=CodeProjectResponse)
async def update_code_project(
    project_id: int,
    data: CodeProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_owned_project(project_id, user.id, db)
    changes = data.model_dump(exclude_unset=True)

    if "folder_id" in changes:
        await validate_owned_folder(changes["folder_id"], user.id, db)

    if changes.get("name") is not None:
        duplicate_file = await db.execute(
            select(CodeFile.id).where(
                CodeFile.project_id == project_id,
                CodeFile.name == changes["name"],
            )
        )
        if duplicate_file.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A file with this name already exists in the project.",
            )

    for field in ("name", "language", "code", "folder_id"):
        if field in changes:
            setattr(project, field, changes[field])

    await db.commit()
    await db.refresh(project)

    return CodeProjectResponse.model_validate(project)


@router.delete("/{project_id}")
async def delete_code_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_owned_project(project_id, user.id, db)
    await db.delete(project)
    await db.commit()

    return {"message": "Code project deleted."}
