from threading import BoundedSemaphore

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.code_execution import (
    CodeExecutionRequest,
    CodeExecutionResponse,
)
from app.services.code_runner import execute_code

router = APIRouter(prefix="/code-execution", tags=["Code Execution"])
_RUN_SLOTS = BoundedSemaphore(2)


@router.post("/run", response_model=CodeExecutionResponse)
async def run_code(
    data: CodeExecutionRequest,
    user: User = Depends(get_current_user),
):
    # The authenticated user is required; execution is deliberately capped
    # to two concurrent jobs per backend process.
    if not _RUN_SLOTS.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The code runner is busy. Try again shortly.",
        )

    try:
        if data.source_files:
            return await execute_code(data.language, data.code, data.stdin, data.source_files)
        return await execute_code(data.language, data.code, data.stdin)
    finally:
        _RUN_SLOTS.release()
