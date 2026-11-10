from fastapi import APIRouter
from app.api.v1.endpoints import health, handover, sentinel, knowledge, radar, documents, recreator, auth, chat, projects

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects & Intake"])
api_router.include_router(handover.router, prefix="/handovers", tags=["Handovers"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(sentinel.router, prefix="/sentinel", tags=["Synora Sentinel"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["Knowledge Graph"])
api_router.include_router(radar.router, prefix="/radar", tags=["Knowledge Loss Radar"])
api_router.include_router(recreator.router, prefix="/recreator", tags=["Environment Recreator"])
api_router.include_router(chat.router, prefix="/chat", tags=["AI Agents & Chat"])
