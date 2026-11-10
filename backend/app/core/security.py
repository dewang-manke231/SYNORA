import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import User, OrganizationMembership, Project, Handover, Document

# Configuration. There is intentionally no signing-secret fallback.
JWT_ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24)

http_bearer_scheme = HTTPBearer(auto_error=False)


def _jwt_secret() -> str:
    secret = settings.JWT_SECRET
    if (
        not secret
        or len(secret.strip()) < 32
        or any(marker in secret.lower() for marker in ("changeme", "change-me", "placeholder", "replace-with", "your-secret", "test-only"))
    ):
        raise RuntimeError("JWT_SECRET must be configured with at least 32 characters before using authentication.")
    return secret.strip()


def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt with salt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a stored bcrypt hash."""
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Creates a signed JWT access token containing subject (user_id), email, role, and expiration."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a signed JWT token."""
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Strict server-side authentication dependency.
    Requires a valid Bearer token in the Authorization header.
    Fails closed with HTTP 401 when unauthenticated.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token in the Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject invalid.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account has been disabled.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Optional authentication dependency for read-only or permissive public endpoints.
    Returns the User if a valid Bearer token is provided, or None.
    If an invalid/expired token is supplied, raises HTTP 401.
    """
    if not credentials or not credentials.credentials:
        return None

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        return None

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    return user


def require_role(required_role: str):
    """
    Server-side role authorization dependency.
    Enforces that the authenticated user possesses the required role (e.g. 'manager', 'admin').
    Fails closed with HTTP 403 Forbidden if role privileges are insufficient.
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Insufficient privileges. Required role: '{required_role}'. Your role: '{current_user.role}'.",
            )
        return current_user
    return role_checker


def get_user_organization_id(user: User, db: Session) -> Optional[str]:
    """Retrieves the primary organization ID for an authenticated user."""
    membership = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id == user.id)
        .first()
    )
    return membership.organization_id if membership else None


def get_accessible_project_ids(user: User, db: Session) -> Optional[List[str]]:
    """Return tenant-scoped project IDs, or None for administrators."""
    if user.role == "admin":
        return None
    return [
        row[0]
        for row in db.query(Project.id)
        .join(OrganizationMembership, Project.organization_id == OrganizationMembership.organization_id)
        .filter(OrganizationMembership.user_id == user.id)
        .distinct()
        .all()
    ]


def verify_project_organization_access(
    project_id: str,
    current_user: User,
    db: Session,
) -> Project:
    """
    Enforces organization-level data isolation.
    Validates that the requested project exists and belongs to the authenticated user's organization.
    Fails closed with HTTP 404 if not found, or HTTP 403 if project belongs to another organization.
    """
    project_membership = db.query(Project, OrganizationMembership.id).outerjoin(
        OrganizationMembership,
        and_(
            Project.organization_id == OrganizationMembership.organization_id,
            OrganizationMembership.user_id == current_user.id,
        ),
    ).filter(Project.id == project_id).first()
    if not project_membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    project, membership_id = project_membership

    # Admins have cross-organization management privileges
    if current_user.role == "admin":
        return project

    if not project.organization_id or not membership_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access projects outside your organization.",
        )

    return project


def verify_handover_organization_access(
    handover_id: str,
    current_user: User,
    db: Session,
) -> Handover:
    """
    Enforces organization-level data isolation and assignment boundaries for handovers.
    """
    handover = db.query(Handover).filter(Handover.id == handover_id).first()
    if not handover:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Handover dossier '{handover_id}' not found.",
        )

    # Admins have cross-organization management privileges
    if current_user.role != "admin":
        user_memberships = (
            db.query(OrganizationMembership.organization_id)
            .filter(OrganizationMembership.user_id == current_user.id)
            .all()
        )
        user_org_ids = {m[0] for m in user_memberships}

        if handover.organization_id:
            if handover.organization_id not in user_org_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: You do not have permission to access handovers outside your organization.",
                )
        elif handover.project_id:
            verify_project_organization_access(handover.project_id, current_user, db)
        else:
            # Unlinked legacy handover without organization_id: only accessible by the original creator
            if current_user.full_name != handover.employee_name:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: Unlinked handover cannot be accessed outside its creator's scope.",
                )

        if handover.project_id:
            verify_project_organization_access(handover.project_id, current_user, db)

    # For employees: enforce assignment boundary if assigned
    if current_user.role == "employee":
        if handover.assigned_to and handover.assigned_to != current_user.id:
            # Check if this employee is the original creator
            if current_user.full_name != handover.employee_name:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: You are not assigned to this handover dossier.",
                )

    return handover


def verify_document_organization_access(
    document_id: str,
    current_user: User,
    db: Session,
) -> Document:
    """
    Enforces organization-level data isolation for documents and persistent storage.
    Fails closed with HTTP 404 if not found, or HTTP 403 if document belongs to an external organization.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )

    # Admins have cross-organization access
    if current_user.role == "admin":
        return doc

    if doc.project_id:
        verify_project_organization_access(doc.project_id, current_user, db)
    elif doc.handover_id:
        verify_handover_organization_access(doc.handover_id, current_user, db)

    return doc

