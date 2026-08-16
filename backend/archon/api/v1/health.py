from fastapi import APIRouter
from archon.config import settings

router = APIRouter()

@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "version": settings.ARCHON_VERSION,
    }
