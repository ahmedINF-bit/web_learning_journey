from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.memory import MemoryResponse, MemoryUpdate
from app.services.memory_service import MemoryService


router = APIRouter(
    prefix="/memories",
    tags=["Memories"],
)


# ========================================================
# GET ALL MEMORIES
# ========================================================

@router.get(
    "",
    response_model=list[MemoryResponse],
)
async def get_memories(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MemoryService(
        db=db,
        user_id=current_user.id,
    )

    return await service.get_memories()

# ========================================================
# UPDATE MEMORY
# ========================================================

@router.put(
    "/{memory_type}",
    response_model=MemoryResponse,
)
async def update_memory(
    memory_type: str,
    memory_data: MemoryUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MemoryService(
        db=db,
        user_id=current_user.id,
    )

    updated_memory = await service.update_memory(
        memory_type=memory_type,
        memory_content=memory_data.content,
    )

    if updated_memory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    return updated_memory


# ========================================================
# DELETE MEMORY
# ========================================================

@router.delete(
    "/{memory_type}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_memory(
    memory_type: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MemoryService(
        db=db,
        user_id=current_user.id,
    )

    deleted = await service.delete_memory(
        memory_type=memory_type,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )