import pytest
import os
from contextlib import asynccontextmanager

# Test-only signing key and demo fixture opt-in; never supplied by application code.
os.environ.setdefault("JWT_SECRET", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
os.environ.setdefault("DEMO_SEED_ENABLED", "true")
os.environ.setdefault("DEMO_LOGIN_ENABLED", "true")
os.environ.setdefault("DEMO_MANAGER_EMAIL", "manager@demo.test")
os.environ.setdefault("DEMO_MANAGER_PASSWORD", "TestManagerPass!2026")
os.environ.setdefault("DEMO_EMPLOYEE_EMAIL", "employee@demo.test")
os.environ.setdefault("DEMO_EMPLOYEE_PASSWORD", "TestEmployeePass!2026")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import app.core.database
import app.core.seed as seed_module
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.core.security import create_access_token
from app.core.seed import seed_database
import app.models  # Ensure all models are registered with Base.metadata

TEST_DATABASE_URL = "sqlite://"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Monkeypatch database engine and sessionmaker so test suite always uses test database
app.core.database.engine = test_engine
app.core.database.SessionLocal = TestingSessionLocal
seed_module.engine = test_engine
seed_module.SessionLocal = TestingSessionLocal

# Preserve local storage for test suite execution
import app.core.config
import app.services.storage
app.core.config.settings.STORAGE_PROVIDER = "local"
app.core.config.settings.EMBEDDING_PROVIDER = "mock"
app.services.storage._storage_instance = app.services.storage.LocalStorageProvider()

# The fixture creates and seeds its isolated database explicitly. Don't run the
# application's production startup initializer against test connections.
@asynccontextmanager
async def _test_lifespan(_app):
    yield

fastapi_app.router.lifespan_context = _test_lifespan



@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

    def get_test_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db] = get_test_db
    yield
    fastapi_app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)



@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def manager_token():
    return create_access_token({
        "sub": "usr-mgr-01",
        "email": "marcus.vance@acme.corp",
        "role": "manager",
        "org_id": "org-acme-01",
    })


@pytest.fixture
def employee_token():
    return create_access_token({
        "sub": "usr-dev-01",
        "email": "alex.mercer@acme.corp",
        "role": "employee",
        "org_id": "org-acme-01",
    })


@pytest.fixture
def client(manager_token):
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app, headers={"Authorization": f"Bearer {manager_token}"}) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def unauthed_client():
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()
