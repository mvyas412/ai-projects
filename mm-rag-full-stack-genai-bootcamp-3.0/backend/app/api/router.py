from fastapi import APIRouter

from backend.app.api.routes.access import router as access_router
from backend.app.api.routes.audit import router as audit_router
from backend.app.api.routes.conversations import router as conversations_router
from backend.app.api.routes.documents import router as documents_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.ingestion import router as ingestion_router
from backend.app.api.routes.users import router as users_router
from backend.app.api.routes.workspaces import router as workspaces_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(users_router)
api_router.include_router(workspaces_router)
api_router.include_router(access_router)
api_router.include_router(documents_router)
api_router.include_router(ingestion_router)
api_router.include_router(conversations_router)
api_router.include_router(audit_router)
