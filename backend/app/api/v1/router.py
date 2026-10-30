from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.chats import router as chats_router
from app.api.v1.folders import router as folders_router
from app.api.v1.notes import router as notes_router
from app.api.v1.files import router as files_router
from app.api.v1.settings import router as settings_router
from app.api.v1.ai_tools import router as ai_router
from app.api.v1.admin import router as admin_router
from app.api.v1.memories import router as memories_router
from app.api.v1.billing import router as billing_router


api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(chats_router)
api_router.include_router(folders_router)
from app.api.v1.code_projects import router as code_projects_router
from app.api.v1.code_execution import router as code_execution_router
from app.api.v1.code_files import router as code_files_router

api_router.include_router(notes_router)
api_router.include_router(code_projects_router)
api_router.include_router(code_execution_router)
api_router.include_router(code_files_router)
api_router.include_router(files_router)
api_router.include_router(settings_router)
api_router.include_router(ai_router)
api_router.include_router(admin_router)
api_router.include_router(memories_router)
api_router.include_router(billing_router)
