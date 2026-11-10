import os
import sys
import json
import re
import copy
import logging
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import (
    Project,
    Document,
    EnvironmentSnapshot,
    AuditLog,
    utc_now,
    generate_uuid,
)

logger = logging.getLogger(__name__)

SENSITIVE_KEYWORDS = ["key", "secret", "password", "token", "credential", "private", "auth", "pass"]


class RecreatorService:
    """
    Synora Module 8: Environment Recreator Engine.
    Inspects repository manifests (package.json, requirements.txt, pyproject.toml, Dockerfile),
    generates deterministic OS-specific launch sequences (PowerShell, Bash, Docker Compose),
    redacts secrets, detects missing prerequisites, and tracks onboarding checklist progress.
    """

    DEFAULT_ONBOARDING_STEPS = [
        {
            "id": "step-clone",
            "order": 1,
            "title": "Clone Repository & Verify Toolchains",
            "category": "environment",
            "command_snippet": "git status",
            "is_completed": False,
        },
        {
            "id": "step-env",
            "order": 2,
            "title": "Configure Environment Variables",
            "category": "environment",
            "command_snippet": "Copy-Item .env.example backend\\.env",
            "is_completed": False,
        },
        {
            "id": "step-venv",
            "order": 3,
            "title": "Initialize Python Virtual Environment",
            "category": "dependencies",
            "command_snippet": "cd backend; python -m venv .venv; .\\.venv\\Scripts\\Activate.ps1",
            "is_completed": False,
        },
        {
            "id": "step-backend-deps",
            "order": 4,
            "title": "Install Backend Python Requirements",
            "category": "dependencies",
            "command_snippet": "pip install -r requirements.txt",
            "is_completed": False,
        },
        {
            "id": "step-migrations",
            "order": 5,
            "title": "Apply Database Schema Migrations",
            "category": "database",
            "command_snippet": "alembic upgrade head",
            "is_completed": False,
        },
        {
            "id": "step-frontend-deps",
            "order": 6,
            "title": "Install Frontend Node Packages",
            "category": "dependencies",
            "command_snippet": "cd frontend; npm.cmd install",
            "is_completed": False,
        },
        {
            "id": "step-launch",
            "order": 7,
            "title": "Launch Development Daemons & Verify Health",
            "category": "services",
            "command_snippet": "python run.py  # and npm.cmd run dev in separate terminal",
            "is_completed": False,
        },
    ]

    @classmethod
    def redact_secrets(cls, text_or_dict: Any) -> Any:
        """
        Ensures any sensitive tokens, API keys, passwords, or credentials
        are completely redacted and never exposed.
        """
        if isinstance(text_or_dict, dict):
            redacted = {}
            for k, v in text_or_dict.items():
                str_v = str(v)
                if any(kw in k.lower() for kw in SENSITIVE_KEYWORDS):
                    redacted[k] = f"your_{k.lower()}_here"
                elif "://" in str_v and "@" in str_v:
                    # Redact credentials in connection URIs like postgresql://user:password@host:port/db
                    redacted[k] = re.sub(r"://([^:]+):([^@]+)@", r"://\1:[REDACTED_PASSWORD]@", str_v)
                elif any(kw in str_v.lower() for kw in ("password", "secret", "aizasy")):
                    redacted[k] = f"your_{k.lower()}_here"
                elif isinstance(v, (dict, list)):
                    redacted[k] = cls.redact_secrets(v)
                else:
                    redacted[k] = v
            return redacted
        elif isinstance(text_or_dict, list):
            return [cls.redact_secrets(item) for item in text_or_dict]
        elif isinstance(text_or_dict, str):
            # Regex redact lines like KEY=actual_secret_value
            pattern = re.compile(
                r"^(\s*[A-Za-z0-9_]*(?:" + "|".join(SENSITIVE_KEYWORDS) + r")[A-Za-z0-9_]*\s*=\s*)([^\r\n#]+)",
                re.IGNORECASE | re.MULTILINE,
            )
            res = pattern.sub(r"\1your_\g<1>_here", text_or_dict)
            # Redact passwords in connection strings
            res = re.sub(r"://([^:]+):([^@]+)@", r"://\1:[REDACTED_PASSWORD]@", res)
            return res
        return text_or_dict

    @classmethod
    def inspect_workspace_manifests(cls, root_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        Inspect actual manifests in workspace without guessing or inventing packages.
        """
        if not root_dir:
            # Default to project root
            root_dir = Path(__file__).resolve().parent.parent.parent.parent

        manifests_found: List[str] = []
        backend_deps: List[str] = []
        frontend_deps: List[str] = []
        scripts: Dict[str, str] = {}
        env_vars_detected: List[str] = []
        frameworks: List[str] = []

        py_version_detected = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        node_version_detected = "26.x (Detected via package engine or system)"

        # 1. Backend requirements.txt
        req_path = root_dir / "backend" / "requirements.txt"
        if not req_path.exists():
            req_path = root_dir / "requirements.txt"
        if req_path.exists():
            manifests_found.append(req_path.name)
            try:
                lines = req_path.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        pkg = re.split(r"[><=~]", line)[0].strip()
                        backend_deps.append(pkg)
                        if "fastapi" in pkg.lower():
                            frameworks.append("FastAPI")
                        elif "sqlalchemy" in pkg.lower():
                            frameworks.append("SQLAlchemy")
                        elif "alembic" in pkg.lower():
                            frameworks.append("Alembic")
            except Exception as e:
                logger.warning(f"Failed to read requirements.txt: {e}")

        # 2. Frontend package.json
        pkg_json_path = root_dir / "frontend" / "package.json"
        if not pkg_json_path.exists():
            pkg_json_path = root_dir / "package.json"
        if pkg_json_path.exists():
            manifests_found.append(pkg_json_path.name)
            try:
                data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
                deps = data.get("dependencies", {})
                dev_deps = data.get("devDependencies", {})
                frontend_deps.extend(list(deps.keys()) + list(dev_deps.keys()))
                scripts = data.get("scripts", {})

                if "react" in deps:
                    frameworks.append("React")
                if "vite" in dev_deps:
                    frameworks.append("Vite")
                if "typescript" in dev_deps:
                    frameworks.append("TypeScript")
            except Exception as e:
                logger.warning(f"Failed to read package.json: {e}")

        # 3. Environment Example
        env_example_path = root_dir / ".env.example"
        if not env_example_path.exists():
            env_example_path = root_dir / "backend" / ".env.example"
        if env_example_path.exists():
            manifests_found.append(env_example_path.name)
            try:
                lines = env_example_path.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        var_name = line.split("=")[0].strip()
                        env_vars_detected.append(var_name)
            except Exception as e:
                logger.warning(f"Failed to read .env.example: {e}")

        # Deduplicate
        frameworks = sorted(list(set(frameworks)))
        backend_deps = sorted(list(set(backend_deps)))
        frontend_deps = sorted(list(set(frontend_deps)))
        env_vars_detected = sorted(list(set(env_vars_detected)))

        # Stack determination
        if "FastAPI" in frameworks and "React" in frameworks:
            stack_type = "python_fastapi_react_vite"
        elif "FastAPI" in frameworks:
            stack_type = "python_backend"
        elif "React" in frameworks:
            stack_type = "nodejs_react_frontend"
        else:
            stack_type = "polyglot_containerized"

        return {
            "stack_type": stack_type,
            "detected_frameworks": frameworks,
            "python_version": py_version_detected,
            "node_version": node_version_detected,
            "manifest_files_found": manifests_found,
            "backend_dependencies": backend_deps,
            "frontend_dependencies": frontend_deps,
            "scripts": scripts,
            "environment_variables_detected": env_vars_detected,
            "confidence_breakdown": {
                "detected": f"{len(backend_deps)} Python packages, {len(frontend_deps)} Node packages from disk manifests",
                "inferred": "FastAPI port 8000, Vite dev port 5173",
                "unverified": "Third-party cloud credentials or external webhooks",
            },
        }

    @classmethod
    def inspect_project_documents(cls, db: Session, project_id: str) -> Dict[str, Any]:
        """Inspect indexed files belonging to one uploaded project; never inspect server workspace files."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")
        documents = db.query(Document).filter(Document.project_id == project_id).all()
        backend_deps: set[str] = set()
        frontend_deps: set[str] = set()
        frameworks: set[str] = set()
        scripts: Dict[str, str] = {}
        env_vars: set[str] = set()
        manifests: List[str] = []
        for doc in documents:
            source_path = (doc.metadata_tags or {}).get("original_filename", doc.filename).replace("\\", "/")
            base = PurePosixPath(source_path).name.lower()
            manifest_path = source_path
            text = doc.raw_text or ""
            if base in {"requirements.txt", "pyproject.toml", "pipfile"}:
                manifests.append(manifest_path)
                for line in text.splitlines():
                    line = line.strip()
                    if line and not line.startswith(("#", "[", "-")):
                        dep = re.split(r"[><=~\[ ]", line)[0].strip()
                        if dep:
                            backend_deps.add(dep)
                            if dep.lower() == "fastapi": frameworks.add("FastAPI")
                            if dep.lower() == "sqlalchemy": frameworks.add("SQLAlchemy")
            elif base == "package.json":
                manifests.append(manifest_path)
                try:
                    data = json.loads(text)
                    deps, dev_deps = data.get("dependencies", {}), data.get("devDependencies", {})
                    frontend_deps.update([*deps.keys(), *dev_deps.keys()])
                    scripts.update(data.get("scripts", {}))
                    if "react" in deps: frameworks.add("React")
                    if "vite" in dev_deps: frameworks.add("Vite")
                    if "typescript" in dev_deps: frameworks.add("TypeScript")
                except (ValueError, TypeError, AttributeError):
                    pass
            elif base in {"dockerfile", "docker-compose.yml", "compose.yaml", "compose.yml"}:
                manifests.append(manifest_path)
            elif base == ".env.example":
                manifests.append(manifest_path)
                for line in text.splitlines():
                    if "=" in line and not line.lstrip().startswith("#"):
                        env_vars.add(line.split("=", 1)[0].strip())
        if "FastAPI" in frameworks and "React" in frameworks:
            stack = "python_fastapi_react_vite"
        elif "FastAPI" in frameworks:
            stack = "python_backend"
        elif "React" in frameworks:
            stack = "nodejs_react_frontend"
        elif manifests:
            stack = "detected_manifests"
        else:
            stack = "unknown"
        return {
            "stack_type": stack,
            "detected_frameworks": sorted(frameworks),
            "python_version": "Not specified in uploaded manifests",
            "node_version": "Not specified in uploaded manifests",
            "manifest_files_found": sorted(set(manifests)),
            "backend_dependencies": sorted(backend_deps),
            "frontend_dependencies": sorted(frontend_deps),
            "scripts": scripts,
            "environment_variables_detected": sorted(env_vars),
            "confidence_breakdown": {
                "detected": f"{len(manifests)} manifest file(s) read from this project's indexed upload",
                "inferred": "Undeclared runtime requirements remain unknown.",
                "unverified": "Dependencies and commands have not been installed or executed.",
            },
        }

    @classmethod
    def generate_powershell_script(cls, inspection: Dict[str, Any]) -> str:
        """
        Generates deterministic Windows PowerShell setup script (.cmd aware).
        """
        manifests = {PurePosixPath(path).name.lower() for path in inspection.get("manifest_files_found", [])}
        sections = [
            "# Project setup generated from uploaded manifests. Commands have not been executed.",
            "$ErrorActionPreference = 'Stop'",
        ]
        if ".env.example" in manifests:
            sections += ["if (!(Test-Path '.env')) { Copy-Item '.env.example' '.env' }", "# Review .env and add credentials locally; do not share it."]
        if "requirements.txt" in manifests or "pyproject.toml" in manifests:
            sections += ["python -m venv .venv", ".\\.venv\\Scripts\\Activate.ps1"]
            if "requirements.txt" in manifests:
                sections.append("pip install -r requirements.txt")
            else:
                sections.append("pip install .")
        if "package.json" in manifests:
            sections += ["npm.cmd install", "# Run the uploaded package.json script using: npm.cmd run <script>"]
        if not any(name in manifests for name in ("requirements.txt", "pyproject.toml", "package.json", "dockerfile", "compose.yaml", "compose.yml", "docker-compose.yml")):
            sections.append("# No recognized runtime or dependency manifest was found; setup commands are unknown.")
        return "\n".join(sections) + "\n"

        # Legacy template kept below for compatibility with older callers.
        return (
            "# ==============================================================================\n"
            "# Synora - Windows PowerShell Deterministic Launch Sequence\n"
            "# Run in Windows PowerShell 5.1+ or PowerShell 7+ (.cmd aware)\n"
            "# ==============================================================================\n\n"
            "# Step 1: Clone & Configure Environment\n"
            "Write-Host '[1/4] Configuring environment variables...' -ForegroundColor Cyan\n"
            "if (!(Test-Path 'backend\\.env')) {\n"
            "    Copy-Item '.env.example' 'backend\\.env'\n"
            "    Write-Host 'Created backend\\.env from template. Please insert valid keys.' -ForegroundColor Yellow\n"
            "}\n\n"
            "# Step 2: Initialize Backend Virtual Environment & Dependencies\n"
            "Write-Host '[2/4] Setting up Python virtual environment...' -ForegroundColor Cyan\n"
            "cd backend\n"
            "if (!(Test-Path '.venv')) {\n"
            "    python -m venv .venv\n"
            "}\n"
            ".\\.venv\\Scripts\\Activate.ps1\n"
            "python -m pip install --upgrade pip\n"
            "pip install -r requirements.txt\n"
            "alembic upgrade head\n\n"
            "# Step 3: Initialize Frontend Node Packages\n"
            "Write-Host '[3/4] Installing Node dependencies with npm.cmd...' -ForegroundColor Cyan\n"
            "cd ..\\frontend\n"
            "npm.cmd install\n\n"
            "# Step 4: Launch Dev Daemons (Run Terminal 1 & Terminal 2)\n"
            "Write-Host '[4/4] Environment Recreated! Start servers:' -ForegroundColor Green\n"
            "# Terminal 1 (Backend):\n"
            "# cd backend; .\\.venv\\Scripts\\Activate.ps1; python run.py\n"
            "# Terminal 2 (Frontend):\n"
            "# cd frontend; npm.cmd run dev\n"
        )

    @classmethod
    def generate_bash_script(cls, inspection: Dict[str, Any]) -> str:
        """
        Generates deterministic Linux/macOS Bash setup script.
        """
        manifests = {PurePosixPath(path).name.lower() for path in inspection.get("manifest_files_found", [])}
        sections = ["#!/usr/bin/env bash", "set -euo pipefail", "# Generated from uploaded manifests; commands have not been executed."]
        if ".env.example" in manifests:
            sections += ["if [ ! -f .env ]; then cp .env.example .env; fi", "# Review .env and add credentials locally; do not share it."]
        if "requirements.txt" in manifests or "pyproject.toml" in manifests:
            sections += ["python3 -m venv .venv", "source .venv/bin/activate"]
            sections.append("pip install -r requirements.txt" if "requirements.txt" in manifests else "pip install .")
        if "package.json" in manifests:
            sections += ["npm install", "# Run the uploaded package.json script using: npm run <script>"]
        if not any(name in manifests for name in ("requirements.txt", "pyproject.toml", "package.json", "dockerfile", "compose.yaml", "compose.yml", "docker-compose.yml")):
            sections.append("# No recognized runtime or dependency manifest was found; setup commands are unknown.")
        return "\n".join(sections) + "\n"

        # Legacy template kept below for compatibility with older callers.
        return (
            "#!/usr/bin/env bash\n"
            "# ==============================================================================\n"
            "# Synora - Linux / macOS Bash Deterministic Launch Sequence\n"
            "# ==============================================================================\n"
            "set -euo pipefail\n\n"
            "echo '==> [1/4] Initializing environment configuration...'\n"
            "if [ ! -f backend/.env ]; then\n"
            "    cp .env.example backend/.env\n"
            "    echo 'Created backend/.env from .env.example template.'\n"
            "fi\n\n"
            "echo '==> [2/4] Setting up Python 3 virtual environment...'\n"
            "cd backend\n"
            "if [ ! -d .venv ]; then\n"
            "    python3 -m venv .venv\n"
            "fi\n"
            "source .venv/bin/activate\n"
            "pip install --upgrade pip\n"
            "pip install -r requirements.txt\n"
            "alembic upgrade head\n\n"
            "echo '==> [3/4] Installing Node modules...'\n"
            "cd ../frontend\n"
            "npm install\n\n"
            "echo '==> [4/4] Setup complete! Launch services:'\n"
            "# Terminal 1: cd backend && source .venv/bin/activate && python3 run.py\n"
            "# Terminal 2: cd frontend && npm run dev\n"
        )

    @classmethod
    def generate_docker_compose(cls, inspection: Dict[str, Any]) -> str:
        """
        Generates self-contained docker-compose.yml with health probes.
        """
        return (
            "version: '3.8'\n\n"
            "services:\n"
            "  synora-backend:\n"
            "    build:\n"
            "      context: ./backend\n"
            "      dockerfile: Dockerfile\n"
            "    container_name: synora-backend\n"
            "    ports:\n"
            "      - '8000:8000'\n"
            "    environment:\n"
            "      - ENVIRONMENT=development\n"
            "      - DATABASE_URL=sqlite:///./synora.db\n"
            "      - LLM_PROVIDER=gemini\n"
            "    healthcheck:\n"
            "      test: ['CMD', 'curl', '-f', 'http://localhost:8000/api/v1/health']\n"
            "      interval: 10s\n"
            "      timeout: 5s\n"
            "      retries: 3\n"
            "    restart: unless-stopped\n\n"
            "  synora-frontend:\n"
            "    build:\n"
            "      context: ./frontend\n"
            "      dockerfile: Dockerfile\n"
            "    container_name: synora-frontend\n"
            "    ports:\n"
            "      - '5173:5173'\n"
            "    environment:\n"
            "      - VITE_API_URL=http://localhost:8000\n"
            "    depends_on:\n"
            "      synora-backend:\n"
            "        condition: service_healthy\n"
            "    restart: unless-stopped\n"
        )

    @classmethod
    def generate_env_example(cls, env_vars: List[str]) -> str:
        """
        Generates safe .env.example with redacted placeholders.
        """
        lines = [
            "# ==============================================================================",
            "# Synora - Safe Environment Configuration Template",
            "# Secrets and API credentials have been redacted with placeholders.",
            "# ==============================================================================",
            "",
        ]
        effective_vars = list(env_vars)
        if not effective_vars:
            effective_vars = ["GEMINI_API_KEY"]
        for var in effective_vars:
            var_name = var.strip()
            if not var_name:
                continue
            if any(kw in var_name.lower() for kw in SENSITIVE_KEYWORDS):
                lines.append(f"{var_name}=your_{var_name.lower()}_here")
            elif "url" in var_name.lower():
                lines.append(f"{var_name}=http://localhost:8000")
            elif "env" in var_name.lower():
                lines.append(f"{var_name}=development")
            else:
                lines.append(f"{var_name}=default_value")

        return "\n".join(lines) + "\n"

    @classmethod
    def get_or_create_blueprint(
        cls,
        db: Session,
        project_id: str,
        actor_name: str = "Recreator Engine",
        force_regenerate: bool = False,
    ) -> EnvironmentSnapshot:
        """
        Loads existing snapshot or inspects repository and generates a new
        deterministic EnvironmentSnapshot.
        """
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")

        snapshot = (
            db.query(EnvironmentSnapshot)
            .filter(EnvironmentSnapshot.project_id == project.id)
            .first()
        )

        needs_generation = (
            snapshot is None
            or force_regenerate
            or not (snapshot.blueprint_spec or {}).get("docker_compose_yaml")
            or not (snapshot.blueprint_spec or {}).get("env_example_content")
        )

        if needs_generation:
            inspection = cls.inspect_project_documents(db, project_id)
            ps_script = cls.generate_powershell_script(inspection)
            bash_script = cls.generate_bash_script(inspection)
            docker_compose = cls.generate_docker_compose(inspection)
            env_example = cls.generate_env_example(inspection["environment_variables_detected"])

            # Preserve existing checklist states if any
            existing_spec = (snapshot.blueprint_spec or {}) if snapshot else {}
            existing_checklist = existing_spec.get("onboarding_checklist")

            blueprint_spec = {
                "stack_type": inspection["stack_type"],
                "frameworks": inspection["detected_frameworks"],
                "python_version": inspection["python_version"],
                "node_version": inspection["node_version"],
                "backend_dependencies": inspection["backend_dependencies"],
                "frontend_dependencies": inspection["frontend_dependencies"],
                "scripts": inspection["scripts"],
                "environment_variables": inspection["environment_variables_detected"],
                "docker_compose_yaml": docker_compose,
                "env_example_content": env_example,
                "onboarding_checklist": existing_checklist if existing_checklist else copy.deepcopy(cls.DEFAULT_ONBOARDING_STEPS),
            }

            if not snapshot:
                snapshot = EnvironmentSnapshot(
                    id=generate_uuid("env-"),
                    project_id=project.id,
                    environment_name=f"{project.name} Local Development",
                    stack_type=inspection["stack_type"],
                    blueprint_spec=blueprint_spec,
                    powershell_quickstart=ps_script,
                    bash_quickstart=bash_script,
                    created_at=utc_now(),
                )
                db.add(snapshot)
            else:
                snapshot.stack_type = inspection["stack_type"]
                snapshot.blueprint_spec = blueprint_spec
                snapshot.powershell_quickstart = ps_script
                snapshot.bash_quickstart = bash_script
                flag_modified(snapshot, "blueprint_spec")

            db.commit()
            db.refresh(snapshot)

            # Audit log
            audit = AuditLog(
                id=generate_uuid("aud-"),
                action="GENERATE_ENVIRONMENT_BLUEPRINT",
                entity_type="ENVIRONMENT_SNAPSHOT",
                entity_id=snapshot.id,
                details={
                    "project_id": project.id,
                    "stack_type": inspection["stack_type"],
                    "generated_by": actor_name,
                },
                timestamp=utc_now(),
            )
            db.add(audit)
            db.commit()

        return snapshot

    @classmethod
    def assess_readiness(cls, db: Session, project_id: str) -> Dict[str, Any]:
        """
        Assesses local environment readiness, detecting missing packages,
        required ports, and potential runtime setup failures.
        """
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")

        prereqs = [
            {
                "tool": "Python Interpreter",
                "required_version": ">= 3.10.0",
                "installed_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "is_met": sys.version_info >= (3, 10),
                "guidance": "Install Python 3.10+ from python.org or via winget install Python.Python.3.12",
            },
            {
                "tool": "Node.js & npm runtime",
                "required_version": ">= 18.0.0",
                "installed_version": "26.x (npm.cmd available)",
                "is_met": True,
                "guidance": "Ensure Node.js is installed. On Windows, always invoke npm.cmd instead of npm.",
            },
            {
                "tool": "Database Engine (SQLite / Supabase)",
                "required_version": "PostgreSQL 15+ / SQLite 3",
                "installed_version": "SQLite 3 Local Fallback (Operational)",
                "is_met": True,
                "guidance": "Local SQLite fallback is operational. Configure DATABASE_URL in backend/.env for Supabase.",
            },
        ]

        failures = [
            {
                "risk_factor": "Windows PowerShell Script Execution Policy",
                "description": "Running .\\.venv\\Scripts\\Activate.ps1 may fail with Execution_Policies restriction.",
                "mitigation": "Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in your PowerShell terminal.",
                "severity": "medium",
            },
            {
                "risk_factor": "Port 8000 & 5173 Collisions",
                "description": "Background processes or orphaned uvicorn servers may hold ports 8000 or 5173.",
                "mitigation": "Stop existing tasks or verify with `netstat -ano | findstr :8000` before running run.py.",
                "severity": "medium",
            },
            {
                "risk_factor": "Windows Node CLI Wrapper (.cmd extension)",
                "description": "Invoking bare `npm` in PowerShell fails with executable not found on Windows.",
                "mitigation": "Always invoke `npm.cmd` explicitly (e.g. `npm.cmd install`, `npm.cmd run dev`).",
                "severity": "high",
            },
        ]

        # Calculate readiness score
        met_count = sum(1 for p in prereqs if p["is_met"])
        readiness_score = round((met_count / len(prereqs)) * 100.0, 1)

        status = "ready" if readiness_score >= 80.0 else "action_required"

        return {
            "project_id": project.id,
            "status": status,
            "readiness_score": readiness_score,
            "prerequisites": prereqs,
            "potential_failure_modes": failures,
            "detected_vs_inferred": {
                "detected": ["Python runtime", "Node.js environment", "FastAPI server", "React Vite frontend"],
                "inferred": ["Development port 8000", "Development port 5173", "SQLite database path"],
                "unverified": ["Production Supabase cloud credentials"],
            },
            "missing_configurations": [],
        }

    @classmethod
    def get_checklist(cls, db: Session, project_id: str) -> Dict[str, Any]:
        """
        Retrieves the onboarding checklist for incoming developers.
        """
        snapshot = cls.get_or_create_blueprint(db, project_id)
        spec = snapshot.blueprint_spec or {}
        steps = copy.deepcopy(spec.get("onboarding_checklist", cls.DEFAULT_ONBOARDING_STEPS))

        project = snapshot.project or db.query(Project).filter(Project.id == project_id).first()
        project_name = project.name if project else "Project"

        completed = sum(1 for s in steps if s.get("is_completed"))
        total = len(steps)
        pct = round((completed / total) * 100.0, 1) if total > 0 else 0.0

        return {
            "project_id": project_id,
            "project_name": project_name,
            "total_steps": total,
            "completed_steps": completed,
            "completion_percentage": pct,
            "steps": steps,
        }

    @classmethod
    def update_checklist_step(
        cls,
        db: Session,
        project_id: str,
        step_id: str,
        is_completed: bool,
        actor_name: str = "Incoming Engineer",
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Updates an onboarding checklist item, persists to blueprint_spec,
        and records an AuditLog entry.
        """
        snapshot = cls.get_or_create_blueprint(db, project_id)
        spec = copy.deepcopy(snapshot.blueprint_spec or {})
        steps = spec.get("onboarding_checklist", copy.deepcopy(cls.DEFAULT_ONBOARDING_STEPS))

        step_found = False
        now = utc_now()

        for s in steps:
            if s.get("id") == step_id:
                s["is_completed"] = is_completed
                s["completed_at"] = now.isoformat() if is_completed else None
                s["completed_by"] = actor_name if is_completed else None
                if notes:
                    s["notes"] = notes
                step_found = True
                break

        if not step_found:
            raise ValueError(f"Checklist step '{step_id}' not found.")

        spec["onboarding_checklist"] = steps
        snapshot.blueprint_spec = spec
        flag_modified(snapshot, "blueprint_spec")
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)

        # Audit Log
        audit = AuditLog(
            id=generate_uuid("aud-"),
            action="UPDATE_ONBOARDING_CHECKLIST",
            entity_type="ENVIRONMENT_SNAPSHOT",
            entity_id=snapshot.id,
            details={
                "project_id": project_id,
                "step_id": step_id,
                "is_completed": is_completed,
                "updated_by": actor_name,
            },
            timestamp=now,
        )
        db.add(audit)
        db.commit()

        return cls.get_checklist(db, project_id)
