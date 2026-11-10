import time
import urllib.parse
from typing import Dict, Any, Optional
from urllib.parse import urlparse
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import settings


def normalize_db_url(raw_url: Optional[str]) -> str:
    """
    Normalizes database URL for SQLAlchemy compatibility:
    - Normalizes legacy 'postgres://' to 'postgresql+psycopg2://'
    - Normalizes 'postgresql://' (no driver) to 'postgresql+psycopg2://'
    - Encodes special characters (such as '@' or ':') inside the password
    - Preserves SQLite schemes: 'sqlite:///...'
    """
    if not raw_url:
        return "sqlite:///./synora.db"
    clean_url = raw_url.strip()
    if clean_url.startswith("postgres://"):
        clean_url = "postgresql+psycopg2://" + clean_url[len("postgres://"):]
    elif clean_url.startswith("postgresql://") and not clean_url.startswith("postgresql+"):
        clean_url = "postgresql+psycopg2://" + clean_url[len("postgresql://"):]

    # Safely handle unencoded special characters in password
    if clean_url.startswith("postgresql"):
        try:
            scheme, rest = clean_url.split("://", 1)
            if "@" in rest:
                creds, host_part = rest.rsplit("@", 1)
                if ":" in creds:
                    user, pwd = creds.split(":", 1)
                    # If password contains unencoded '@', encode it
                    if "@" in pwd or ("%" not in pwd and ":" in pwd):
                        pwd = urllib.parse.quote_plus(pwd)
                    clean_url = f"{scheme}://{user}:{pwd}@{host_part}"
        except Exception:
            pass

    return clean_url


def mask_database_url(raw_url: Optional[str]) -> str:
    """
    Returns an abstract database target indicator for health and status endpoints.
    Strictly redacted: returns only 'managed-cloud' or 'local'.
    Never exposes database URLs, hostnames, ports, cloud providers, connection strings, or credentials.
    """
    if not raw_url:
        return "none"
    clean = raw_url.strip().lower()
    if clean.startswith("sqlite"):
        return "local"
    if "postgres" in clean:
        return "managed-cloud"
    return "external"


# Dialect abstraction
raw_db_url = getattr(settings, "DATABASE_URL", "sqlite:///./synora.db")
db_url = normalize_db_url(raw_db_url)
is_sqlite = db_url.startswith("sqlite")

connect_args: Dict[str, Any] = {}

if is_sqlite:
    connect_args = {"check_same_thread": False}
    engine = create_engine(
        db_url,
        connect_args=connect_args,
        echo=False,
    )
else:
    # Supabase PostgreSQL configuration with recommended pool settings
    # pool_pre_ping=True prevents connection dropouts on cloud idle
    # sslmode=require ensures secure encrypted communication with Supabase
    connect_args = {
        "sslmode": "require",
        "connect_timeout": 15,
    }
    engine = create_engine(
        db_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
        pool_timeout=30,
        echo=False,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency that provides a database session per request."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connectivity(db: Session) -> Dict[str, Any]:
    """
    Performs a live connectivity check and non-sensitive diagnostics.
    Never returns passwords, secret keys, or unmasked credentials.
    """
    dialect_name = engine.dialect.name  # 'postgresql' or 'sqlite'
    masked_target = mask_database_url(db_url)
    t0 = time.perf_counter()
    
    try:
        db.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        
        # Check pgvector extension on PostgreSQL
        pgvector_active = False
        if dialect_name == "postgresql":
            try:
                res = db.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'")).fetchone()
                pgvector_active = bool(res)
            except Exception:
                pgvector_active = False

        # Count tables
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        
        return {
            "connected": True,
            "dialect": dialect_name,
            "target": masked_target,
            "latency_ms": latency_ms,
            "tables_count": len(table_names),
            "pgvector_active": pgvector_active,
        }
    except Exception as e:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "connected": False,
            "dialect": dialect_name,
            "target": masked_target,
            "latency_ms": latency_ms,
            "tables_count": 0,
            "pgvector_active": False,
            "error": "database_connection_failed",
        }


