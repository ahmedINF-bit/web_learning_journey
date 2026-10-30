from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.code_file import CodeFile
from app.models.code_project import CodeProject
from app.models.user import User
from app.schemas.code_file import (
    CodeFileCreate,
    CodeFileResponse,
    CodeFileUpdate,
)

router = APIRouter(
    prefix="/code-projects/{project_id}/files",
    tags=["Code Project Files"],
)

_ALLOWED_EXTENSIONS = {
    "c": {".c", ".h"},
    "python": {".py"},
    "javascript": {".js", ".mjs"},
}


def validate_file_details(name: str, language: str) -> None:
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix not in _ALLOWED_EXTENSIONS[language]:
        expected = ", ".join(sorted(_ALLOWED_EXTENSIONS[language]))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The file extension for {language} must be one of: {expected}.",
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


async def get_project_file(
    project_id: int,
    file_id: int,
    db: AsyncSession,
) -> CodeFile:
    result = await db.execute(
        select(CodeFile).where(
            CodeFile.id == file_id,
            CodeFile.project_id == project_id,
        )
    )
    code_file = result.scalar_one_or_none()
    if code_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code file not found.",
        )
    return code_file


async def ensure_name_available(
    project_id: int,
    name: str,
    db: AsyncSession,
    exclude_file_id: int | None = None,
) -> None:
    project_result = await db.execute(
        select(CodeProject).where(
            CodeProject.id == project_id,
            CodeProject.name == name,
        )
    )
    if project_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A file with this name already exists in the project.",
        )

    query = select(CodeFile).where(
        CodeFile.project_id == project_id,
        CodeFile.name == name,
    )
    result = await db.execute(query)
    existing = result.scalar_one_or_none()
    if existing is not None and existing.id != exclude_file_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A file with this name already exists in the project.",
        )


@router.get("", response_model=list[CodeFileResponse])
async def list_code_files(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_owned_project(project_id, user.id, db)
    result = await db.execute(
        select(CodeFile)
        .where(CodeFile.project_id == project_id)
        .order_by(CodeFile.created_at, CodeFile.id)
    )
    return [CodeFileResponse.model_validate(item) for item in result.scalars().all()]


@router.post(
    "",
    response_model=CodeFileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_code_file(
    project_id: int,
    data: CodeFileCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_owned_project(project_id, user.id, db)
    validate_file_details(data.name, data.language)
    await ensure_name_available(project_id, data.name, db)

    code_file = CodeFile(
        project_id=project_id,
        name=data.name,
        language=data.language,
        code=data.code,
    )
    db.add(code_file)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A file with this name already exists in the project.",
        )
    await db.refresh(code_file)
    return CodeFileResponse.model_validate(code_file)


@router.put("/{file_id}", response_model=CodeFileResponse)
async def update_code_file(
    project_id: int,
    file_id: int,
    data: CodeFileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_owned_project(project_id, user.id, db)
    code_file = await get_project_file(project_id, file_id, db)
    changes = data.model_dump(exclude_unset=True)

    name = changes.get("name") or code_file.name
    language = changes.get("language") or code_file.language
    validate_file_details(name, language)

    if "name" in changes:
        await ensure_name_available(
            project_id,
            changes["name"],
            db,
            exclude_file_id=file_id,
        )

    for field in ("name", "language", "code"):
        if field in changes and changes[field] is not None:
            setattr(code_file, field, changes[field])

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A file with this name already exists in the project.",
        )
    await db.refresh(code_file)
    return CodeFileResponse.model_validate(code_file)


@router.delete("/{file_id}")
async def delete_code_file(
    project_id: int,
    file_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_owned_project(project_id, user.id, db)
    code_file = await get_project_file(project_id, file_id, db)
    await db.delete(code_file)
    await db.commit()
    return {"message": "Code file deleted."}
