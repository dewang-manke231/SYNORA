from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.schemas.common import HealthStatus
from app.core.config import settings
from app.core.database import get_db, check_db_connectivity
from app.core.security import get_current_user
from app.models import User

router = APIRouter()


@router.get("/health", response_model=HealthStatus)
def health_check(db: Session = Depends(get_db)) -> HealthStatus:
    """
    Public platform health, version, and sanitized database status.
    Strictly redacted: never exposes database URLs, hostnames, connection strings,
    pool status, credentials, or internal infrastructure details.
    """
    telemetry = check_db_connectivity(db)
    is_connected = telemetry.get("connected", False)
    db_status = "connected" if is_connected else "unreachable"

    return HealthStatus(
        status="healthy" if is_connected else "degraded",
        version=settings.VERSION,
        service=settings.PROJECT_NAME,
        database=db_status,
        database_type=telemetry.get("dialect", "unknown"),
        database_target=telemetry.get("target", "none"),
        pgvector_installed=telemetry.get("pgvector_active", False),
        latency_ms=telemetry.get("latency_ms"),
        tables_count=telemetry.get("tables_count", 0),
    )


@router.get("/health/diagnostics")
def internal_diagnostics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Authenticated internal diagnostics endpoint for authorized operators.
    Requires authentication. Still redacts raw credentials.
    """
    telemetry = check_db_connectivity(db)
    return {
        "status": "healthy" if telemetry.get("connected") else "degraded",
        "version": settings.VERSION,
        "caller": current_user.email,
        "role": current_user.role,
        "telemetry": telemetry,
    }
