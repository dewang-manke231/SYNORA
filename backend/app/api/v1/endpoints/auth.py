import re
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.seed import PUBLIC_DEMO_ORGANIZATION_ID, PUBLIC_DEMO_ROLE_USER_IDS
from app.models import User, Organization, OrganizationMembership, generate_uuid, utc_now
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_user_organization_id,
    require_role,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.schemas.common import (
    UserRegisterRequest,
    EmployeeCreateRequest,
    UserLoginRequest,
    DemoLoginRequest,
    PublicDemoCredentials,
    TokenResponse,
    UserResponse,
)

router = APIRouter()

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")


@router.get("/demo-credentials", response_model=PublicDemoCredentials)
def get_public_demo_credentials() -> PublicDemoCredentials:
    """Expose only the intentionally public credentials for the isolated demo."""
    if not settings.DEMO_LOGIN_ENABLED or not settings.DEMO_SEED_ENABLED:
        raise HTTPException(status_code=404, detail="Public demo login is disabled.")
    if not all((settings.DEMO_MANAGER_EMAIL, settings.DEMO_MANAGER_PASSWORD,
                settings.DEMO_EMPLOYEE_EMAIL, settings.DEMO_EMPLOYEE_PASSWORD)):
        raise HTTPException(status_code=503, detail="Public demo credentials are not configured.")
    return PublicDemoCredentials(
        manager={"email": settings.DEMO_MANAGER_EMAIL, "password": settings.DEMO_MANAGER_PASSWORD},
        employee={"email": settings.DEMO_EMPLOYEE_EMAIL, "password": settings.DEMO_EMPLOYEE_PASSWORD},
    )


@router.post("/employees", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_organization_employee(
    payload: EmployeeCreateRequest,
    current_user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Create an employee account in the authenticated manager's organization."""
    organization_id = get_user_organization_id(current_user, db)
    if not organization_id:
        raise HTTPException(status_code=403, detail="Manager must belong to an organization before adding employees.")
    clean_email = payload.email.strip().lower()
    clean_name = payload.full_name.strip()
    if not EMAIL_REGEX.match(clean_email):
        raise HTTPException(status_code=400, detail="Invalid email address format.")
    if not clean_name:
        raise HTTPException(status_code=400, detail="Employee name cannot be blank.")
    if db.query(User).filter(User.email == clean_email).first():
        raise HTTPException(status_code=409, detail="A user with this email address already exists.")

    employee = User(
        id=generate_uuid("usr-"), email=clean_email, full_name=clean_name, role="employee",
        hashed_password=hash_password(payload.password), is_active=True, created_at=utc_now(),
    )
    db.add(employee)
    db.flush()
    db.add(OrganizationMembership(
        id=generate_uuid("mem-"), organization_id=organization_id,
        user_id=employee.id, role="member", created_at=utc_now(),
    ))
    db.commit()
    db.refresh(employee)
    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    return UserResponse(
        id=employee.id, email=employee.email, full_name=employee.full_name,
        role=employee.role, organization_id=organization_id,
        organization_name=organization.name if organization else None,
        is_active=employee.is_active, created_at=employee.created_at,
    )


def _issue_session(user: User, db: Session) -> TokenResponse:
    org_id = get_user_organization_id(user, db)
    org = db.query(Organization).filter(Organization.id == org_id).first() if org_id else None
    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role, "org_id": org_id})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse(
            id=user.id, email=user.email, full_name=user.full_name, role=user.role,
            organization_id=org_id, organization_name=org.name if org else None,
            is_active=user.is_active, created_at=user.created_at,
        ),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserRegisterRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    Registers a new user with bcrypt password hashing and issues a signed JWT access token.
    Enforces password length (>= 8 chars), valid email format, and unique email constraint.
    """
    clean_email = payload.email.strip().lower()
    if not EMAIL_REGEX.match(clean_email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email address format.",
        )

    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters in length.",
        )

    # Check for existing user
    existing_user = db.query(User).filter(User.email == clean_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists.",
        )

    # Public self-registration cannot grant privileged roles. Managers/admins
    # must be provisioned through an existing trusted administrative process.
    role = "employee"

    # Create or resolve organization
    org_name = (payload.organization_name or "Default Organization").strip()
    org_slug = re.sub(r"[^\w\-]", "-", org_name.lower())[:80]
    org = db.query(Organization).filter(
        (Organization.slug == org_slug) | (Organization.name == org_name)
    ).first()
    if not org:
        org = Organization(
            id=generate_uuid("org-"),
            name=org_name,
            slug=org_slug,
            description=f"Workspace organization for {org_name}",
            created_at=utc_now(),
        )
        db.add(org)
        db.flush()

    # Hash password with bcrypt
    hashed_pw = hash_password(payload.password)

    # Create User
    new_user = User(
        id=generate_uuid("usr-"),
        email=clean_email,
        full_name=payload.full_name.strip(),
        role=role,
        hashed_password=hashed_pw,
        is_active=True,
        created_at=utc_now(),
    )
    db.add(new_user)
    db.flush()

    # Create Organization Membership
    membership = OrganizationMembership(
        id=generate_uuid("mem-"),
        organization_id=org.id,
        user_id=new_user.id,
        role="member",
        created_at=utc_now(),
    )
    db.add(membership)
    db.commit()
    db.refresh(new_user)

    # Issue JWT token
    token = create_access_token({
        "sub": new_user.id,
        "email": new_user.email,
        "role": new_user.role,
        "org_id": org.id,
    })

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse(
            id=new_user.id,
            email=new_user.email,
            full_name=new_user.full_name,
            role=new_user.role,
            organization_id=org.id,
            organization_name=org.name,
            is_active=new_user.is_active,
            created_at=new_user.created_at,
        ),
    )


@router.post("/login", response_model=TokenResponse)
def login_user(
    payload: UserLoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    Authenticates a user using email and password, returning a signed JWT access token.
    Fails closed with HTTP 401 Unauthorized on invalid credentials.
    """
    clean_email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()

    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account has been disabled.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _issue_session(user, db)


@router.post("/demo-login", response_model=TokenResponse)
def demo_login(payload: DemoLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Issues a normal RBAC session for a role-specific demo identity."""
    if not settings.DEMO_LOGIN_ENABLED or settings.ENVIRONMENT.strip().lower() == "production":
        raise HTTPException(status_code=404, detail="Direct demo sign-in is disabled on this environment.")

    if settings.ENVIRONMENT.strip().lower() == "production":
        user = db.query(User).filter(User.id == PUBLIC_DEMO_ROLE_USER_IDS[payload.role]).first()
        demo_membership = db.query(OrganizationMembership).filter_by(
            user_id=PUBLIC_DEMO_ROLE_USER_IDS[payload.role],
            organization_id=PUBLIC_DEMO_ORGANIZATION_ID,
            role=payload.role,
        ).first()
        if not demo_membership:
            user = None
    else:
        demo_emails = {
            "manager": "marcus.vance@acme.corp",
            "employee": "alex.mercer@acme.corp",
        }
        user = db.query(User).filter(User.email == demo_emails[payload.role]).first()
    if not user or not user.is_active or user.role != payload.role:
        raise HTTPException(status_code=503, detail=f"The {payload.role} demo account is not available.")
    return _issue_session(user, db)


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    Returns the profile and organization scope of the currently authenticated user.
    """
    org_id = get_user_organization_id(current_user, db)
    org_name = None
    if org_id:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        org_name = org.name if org else None

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        organization_id=org_id,
        organization_name=org_name,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )

