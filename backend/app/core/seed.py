"""
Database Seeding Module for Synora

Seeds realistic enterprise baseline records across all entities:
- Default enterprise organization & admin/manager users
- Core production projects (Payments & Settlement, Data Ingestion, Auth Platform)
- Handover dossiers with complete lifecycle fields
- Sentinel continuity risk alerts
- Knowledge loss radar gap indicators
- Extracted knowledge graph nodes & relationships
- Environment recreate specs
"""
from datetime import datetime, timezone
import secrets
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import SessionLocal, engine, Base
from app.core.embeddings import get_embedding_provider
from app.core.security import hash_password, verify_password
from app.models import (
    User,
    Organization,
    OrganizationMembership,
    Project,
    KnowledgeSource,
    Document,
    DocumentChunk,
    ExtractedKnowledge,
    KnowledgeRelationship,
    VerificationRecord,
    Handover,
    KnowledgeLossIndicator,
    SentinelEvent,
    EnvironmentSnapshot,
    AuditLog,
)

PUBLIC_DEMO_ORGANIZATION_ID = "org-synora-public-demo"
PUBLIC_DEMO_MANAGER_ID = "usr-synora-demo-manager"
PUBLIC_DEMO_EMPLOYEE_ID = "usr-synora-demo-employee"
PUBLIC_DEMO_PROJECT_ID = "prj-synora-public-demo"
PUBLIC_DEMO_ROLE_USER_IDS = {
    "manager": PUBLIC_DEMO_MANAGER_ID,
    "employee": PUBLIC_DEMO_EMPLOYEE_ID,
}


def _seed_public_demo_workspace(db: Session) -> None:
    """Create a clearly labeled sample workspace isolated from customer organizations."""
    organization = db.query(Organization).filter(Organization.id == PUBLIC_DEMO_ORGANIZATION_ID).first()
    if organization and organization.slug != "synora-public-demo":
        raise RuntimeError("The reserved public demo organization ID is already in use.")
    if not organization:
        slug_owner = db.query(Organization).filter(Organization.slug == "synora-public-demo").first()
        if slug_owner:
            raise RuntimeError("The reserved public demo organization slug is already in use.")
        organization = Organization(
            id=PUBLIC_DEMO_ORGANIZATION_ID,
            name="Synora Public Demo Workspace",
            slug="synora-public-demo",
            description="Isolated sample workspace. All content is fictional and for demonstration only.",
        )
        db.add(organization)
        db.flush()

    demo_users = {
        "manager": (PUBLIC_DEMO_MANAGER_ID, settings.DEMO_MANAGER_EMAIL, settings.DEMO_MANAGER_PASSWORD, "Demo Manager"),
        "employee": (PUBLIC_DEMO_EMPLOYEE_ID, settings.DEMO_EMPLOYEE_EMAIL, settings.DEMO_EMPLOYEE_PASSWORD, "Demo Employee"),
    }
    users = {}
    for role, (user_id, email, password, full_name) in demo_users.items():
        user = db.query(User).filter(User.id == user_id).first()
        email_owner = db.query(User).filter(User.email == email).first()
        if email_owner and email_owner.id != user_id:
            raise RuntimeError("A reserved public demo email is already in use.")
        if user and user.role != role:
            raise RuntimeError("A reserved public demo user ID is already in use.")
        if not user:
            user = User(
                id=user_id,
                email=email,
                full_name=full_name,
                role=role,
                hashed_password=hash_password(password),
                is_active=True,
            )
            db.add(user)
            db.flush()
        else:
            # These reserved IDs are owned by the demo workspace. Reconcile configured
            # credentials on restart without resetting an unchanged password hash.
            user.email = email
            user.full_name = full_name
            if not user.hashed_password or not verify_password(password, user.hashed_password):
                user.hashed_password = hash_password(password)
            db.add(user)

        memberships = db.query(OrganizationMembership).filter(
            OrganizationMembership.user_id == user_id
        ).all()
        if any(membership.organization_id != PUBLIC_DEMO_ORGANIZATION_ID for membership in memberships):
            raise RuntimeError("A public demo user is attached to a non-demo organization.")
        demo_membership = next((m for m in memberships if m.organization_id == PUBLIC_DEMO_ORGANIZATION_ID), None)
        if demo_membership and demo_membership.role != role:
            raise RuntimeError("A public demo user has an invalid demo organization role.")
        if not demo_membership:
            db.add(OrganizationMembership(
                id=f"mem-{user_id}",
                organization_id=PUBLIC_DEMO_ORGANIZATION_ID,
                user_id=user_id,
                role=role,
            ))
        users[role] = user

    project = db.query(Project).filter(Project.id == PUBLIC_DEMO_PROJECT_ID).first()
    if project and project.organization_id != PUBLIC_DEMO_ORGANIZATION_ID:
        raise RuntimeError("The reserved public demo project ID is already in use.")
    if not project:
        project = Project(
            id=PUBLIC_DEMO_PROJECT_ID,
            organization_id=PUBLIC_DEMO_ORGANIZATION_ID,
            name="Continuity Sample Project",
            slug="continuity-sample-project",
            description="Fictional project used to demonstrate Synora. Findings and handover below are sample content.",
            bus_factor=1.0,
            knowledge_coverage_score=60.0,
        )
        db.add(project)
        db.flush()

    if not db.query(KnowledgeLossIndicator).filter_by(id="rad-synora-demo-gap").first():
        db.add(KnowledgeLossIndicator(
            id="rad-synora-demo-gap",
            project_id=PUBLIC_DEMO_PROJECT_ID,
            module_name="Sample API Service",
            gap_type="ADR_MISSING",
            severity="medium",
            description="Demo sample: no architecture decision record is linked to the sample API service.",
            recommended_remediation="Document the service's main design decisions and trade-offs.",
        ))
    if not db.query(SentinelEvent).filter_by(id="risk-synora-demo-risk").first():
        db.add(SentinelEvent(
            id="risk-synora-demo-risk",
            project_id=PUBLIC_DEMO_PROJECT_ID,
            project_name=project.name,
            risk_level="medium",
            category="knowledge_continuity",
            description="Demo sample: the sample service has no recorded secondary maintainer.",
            recommended_action="Record a backup owner and review the service handover.",
        ))
    if not db.query(Handover).filter_by(id="ho-synora-demo-handover").first():
        db.add(Handover(
            id="ho-synora-demo-handover",
            organization_id=PUBLIC_DEMO_ORGANIZATION_ID,
            project_id=PUBLIC_DEMO_PROJECT_ID,
            project_name=project.name,
            project_description="Fictional continuity sample for the public demo workspace.",
            employee_name="Demo Employee",
            role="Software Engineer",
            department="Sample Engineering",
            transition_type="project_transfer",
            status="submitted",
            readiness_score=60.0,
            key_responsibilities=["Maintain the sample API service"],
            critical_dependencies=["Sample deployment pipeline"],
            unresolved_blockers=["Sample: architecture decision record is not documented"],
            completed_tasks=["Reviewed the sample service"],
            pending_tasks=["Write the sample architecture decision record"],
            important_notes="Demo sample only. This handover does not describe a real employee or project.",
            recommended_next_actions=["Review service ownership", "Document design decisions"],
            repository_links=[],
            documentation_links=[],
            database_references=[],
            assigned_to=PUBLIC_DEMO_EMPLOYEE_ID,
        ))
    db.commit()


def seed_database(db: Session) -> None:
    if not settings.DEMO_SEED_ENABLED:
        return

    if settings.ENVIRONMENT.strip().lower() == "production":
        _seed_public_demo_workspace(db)
        return

    if settings.ENVIRONMENT.strip().lower() not in {"development", "test"}:
        return

    # Provision the same isolated account pair locally; the Acme fixture below remains
    # a separate development/test dataset and is never used by the public login UI.
    _seed_public_demo_workspace(db)

    # Ensure baseline Acme demo organization and users exist for legacy tests only.
    acme_org = db.query(Organization).filter(Organization.id == "org-acme-01").first()
    if acme_org:
        return

    # 1. Organization
    org = Organization(
        id="org-acme-01",
        name="Acme Financial Technologies",
        slug="acme-fintech",
        description="Global enterprise infrastructure and transaction processing platform.",
    )
    db.add(org)
    db.flush()

    # 2. Users
    admin = User(
        id="usr-admin-01",
        email="admin@acme.corp",
        full_name="Elena Rostova",
        role="admin",
        hashed_password=hash_password(secrets.token_urlsafe(48)),
        is_active=True,
    )
    manager = User(
        id="usr-mgr-01",
        email="marcus.vance@acme.corp",
        full_name="Marcus Vance",
        role="manager",
        hashed_password=hash_password(secrets.token_urlsafe(48)),
        is_active=True,
    )
    dev_alex = User(
        id="usr-dev-01",
        email="alex.mercer@acme.corp",
        full_name="Alex Mercer",
        role="employee",
        hashed_password=hash_password(secrets.token_urlsafe(48)),
        is_active=True,
    )
    dev_sarah = User(
        id="usr-dev-02",
        email="sarah.chen@acme.corp",
        full_name="Sarah Chen",
        role="employee",
        hashed_password=hash_password(secrets.token_urlsafe(48)),
        is_active=True,
    )
    db.add_all([admin, manager, dev_alex, dev_sarah])
    db.flush()

    # 3. Memberships
    db.add_all([
        OrganizationMembership(id="mem-01", organization_id=org.id, user_id=admin.id, role="admin"),
        OrganizationMembership(id="mem-02", organization_id=org.id, user_id=manager.id, role="manager"),
        OrganizationMembership(id="mem-03", organization_id=org.id, user_id=dev_alex.id, role="member"),
        OrganizationMembership(id="mem-04", organization_id=org.id, user_id=dev_sarah.id, role="member"),
    ])
    db.flush()

    # 4. Projects
    prj_payments = Project(
        id="prj-pay-01",
        organization_id=org.id,
        name="Payments & Settlement Engine",
        slug="payments-settlement",
        description="Distributed multi-region transaction processing engine running Raft consensus.",
        repository_url="https://github.com/acme-fintech/payments-core",
        bus_factor=1.0,
        knowledge_coverage_score=68.5,
    )
    prj_data = Project(
        id="prj-data-01",
        organization_id=org.id,
        name="Data Ingestion Pipeline",
        slug="data-ingestion",
        description="Real-time CDC streaming pipeline syncing MySQL/PostgreSQL to BigQuery/Snowflake.",
        repository_url="https://github.com/acme-fintech/data-stream",
        bus_factor=1.2,
        knowledge_coverage_score=82.0,
    )
    prj_auth = Project(
        id="prj-auth-01",
        organization_id=org.id,
        name="Auth & Identity Platform",
        slug="auth-identity",
        description="OAuth2/OIDC centralized identity service and RBAC token validator.",
        repository_url="https://github.com/acme-fintech/auth-svc",
        bus_factor=2.0,
        knowledge_coverage_score=91.0,
    )
    db.add_all([prj_payments, prj_data, prj_auth])
    db.flush()

    # 5. Handover Records (Enhanced structured lifecycle data)
    ho_alex = Handover(
        id="ho-101",
        organization_id=org.id,
        project_id=prj_payments.id,
        project_name="Payments & Settlement Engine",
        project_description="Distributed multi-region transaction processing engine running Raft consensus.",
        employee_name="Alex Mercer",
        role="Lead Systems Architect",
        department="Core Infrastructure",
        transition_type="resignation",
        status="submitted",
        readiness_score=68.0,
        key_responsibilities=[
            "Distributed Consensus Cluster Maintenance",
            "Multi-region failover automation",
            "Core payment gateway integrations",
        ],
        critical_dependencies=[
            "K8s ingress routing configuration tokens",
            "Stripe webhook reconciliation pipeline",
        ],
        unresolved_blockers=[
            "Missing documentation for cross-region data replication script",
        ],
        completed_tasks=[
            "Migrated settlement queue from RabbitMQ to Apache Kafka",
            "Configured mutual TLS between payment worker nodes",
            "Recorded architectural rationale for ledger immutability in ADR-104",
        ],
        pending_tasks=[
            "Shadow session with Marcus Vance on emergency quorum recovery",
            "Transfer ownership of Cloudflare DNS failover tokens",
        ],
        important_notes="If cross-region latency exceeds 120ms, Raft quorum will initiate leader re-election automatically. Do not manually restart pods during this interval.",
        recommended_next_actions=[
            "Pair with Marcus Vance before Nov 11 to test split-brain failover script",
            "Revoke legacy API key credentials from vault namespace /prod/settlement",
        ],
        repository_links=[
            "https://github.com/acme-fintech/payments-core",
            "https://github.com/acme-fintech/settlement-workers",
        ],
        documentation_links=[
            "https://wiki.acme.corp/display/ENG/Payment+Failover+Runbook",
        ],
        database_references=[
            "db.payments.transactions_partitioned",
            "db.payments.ledger_snapshots",
        ],
    )
    ho_sarah = Handover(
        id="ho-102",
        organization_id=org.id,
        project_id=prj_data.id,
        project_name="Data Ingestion Pipeline",
        project_description="Real-time CDC streaming pipeline syncing MySQL/PostgreSQL to BigQuery/Snowflake.",
        employee_name="Sarah Chen",
        role="Senior Data Engineer",
        department="Data Platform",
        transition_type="internal_transition",
        status="verified",
        readiness_score=95.0,
        reviewed_by="Marcus Vance",
        reviewed_at=datetime.now(timezone.utc),
        review_decision="approved",
        review_notes="All CDC pipeline specifications and schema registry credentials verified.",
        key_responsibilities=[
            "CDC pipelines into Snowflake & BigQuery",
            "Real-time event schema catalog maintenance",
        ],
        critical_dependencies=[
            "Kafka schema registry ACLs",
            "Airflow DAG orchestration DAGs",
        ],
        unresolved_blockers=[],
        completed_tasks=[
            "Automated backfill pipeline for transactions history",
            "Configured Dead Letter Queue alerts in PagerDuty",
        ],
        pending_tasks=[],
        important_notes="Airflow DAGs trigger at 01:00 UTC daily. Schema changes must be backward-compatible (Avro format).",
        recommended_next_actions=[
            "Add primary on-call rotation entry for new data engineering hire",
        ],
        repository_links=["https://github.com/acme-fintech/data-stream"],
        documentation_links=["https://wiki.acme.corp/display/DATA/CDC+Architecture"],
        database_references=["db.analytics.raw_events_cdc"],
    )
    db.add_all([ho_alex, ho_sarah])

    # 6. Sentinel Events
    risk_01 = SentinelEvent(
        id="risk-01",
        project_id=prj_payments.id,
        project_name="Payments & Settlement Engine",
        risk_level="critical",
        category="single_point_of_failure",
        description="Alex Mercer is the sole maintainer with write access to multi-region consensus failover scripts.",
        recommended_action="Execute Synora Guided Handover and pair with Secondary SRE engineer.",
        is_resolved=False,
    )
    risk_02 = SentinelEvent(
        id="risk-02",
        project_id=prj_data.id,
        project_name="Data Ingestion Pipeline",
        risk_level="high",
        category="undocumented_workflow",
        description="CDC Kafka stream retry logic has undocumented manual offset override procedures.",
        recommended_action="Generate auto-documentation via Synora Code/Commit Extraction pipeline.",
        is_resolved=False,
    )
    risk_03 = SentinelEvent(
        id="risk-03",
        project_id=prj_auth.id,
        project_name="Auth & Identity Platform",
        risk_level="medium",
        category="missing_ownership",
        description="OAuth legacy token renewal worker has no assigned primary or backup owner after recent team reorganization.",
        recommended_action="Assign primary ownership to Core Security team and run continuity audit.",
        is_resolved=False,
    )
    db.add_all([risk_01, risk_02, risk_03])

    # 7. Knowledge Loss Radar Indicators
    radar_01 = KnowledgeLossIndicator(
        id="rad-01",
        project_id=prj_payments.id,
        module_name="Raft Consensus Failover Script",
        gap_type="ADR_MISSING",
        severity="critical",
        description="No architectural decision record exists documenting quorum election timeouts under network split scenarios.",
        recommended_remediation="Conduct structured architecture extraction interview with Alex Mercer before last working day.",
        is_resolved=False,
    )
    radar_02 = KnowledgeLossIndicator(
        id="rad-02",
        project_id=prj_payments.id,
        module_name="Multi-Region Ingress Routing",
        gap_type="SECONDARY_OWNER_MISSING",
        severity="high",
        description="Only one engineer has access and expertise on AWS/Cloudflare cross-region DNS failover policies.",
        recommended_remediation="Assign SRE peer shadowing session and produce verified handover dossier.",
        is_resolved=False,
    )
    radar_03 = KnowledgeLossIndicator(
        id="rad-03",
        project_id=prj_data.id,
        module_name="Kafka Offset Rebalance Handler",
        gap_type="STALE_DOCUMENTATION",
        severity="medium",
        description="Confluence documentation for stream offset recovery has not been updated in 140 days.",
        recommended_remediation="Trigger automated git commit extraction to refresh operational runbooks.",
        is_resolved=False,
    )
    db.add_all([radar_01, radar_02, radar_03])

    # 8. Knowledge Nodes
    kn_1 = ExtractedKnowledge(
        id="kn-1",
        project_id=prj_payments.id,
        label="Consensus Clustering Engine",
        category="architecture",
        details="Raft consensus implementation managing distributed database state transitions and quorum leaders.",
        owner="Alex Mercer",
        confidence_score=0.95,
        verification_status="verified",
    )
    kn_2 = ExtractedKnowledge(
        id="kn-2",
        project_id=prj_data.id,
        label="Kafka CDC Ingestion",
        category="module",
        details="Real-time Change Data Capture streaming from MySQL to Snowflake / BigQuery with schema registry validation.",
        owner="Sarah Chen",
        confidence_score=0.92,
        verification_status="verified",
    )
    kn_3 = ExtractedKnowledge(
        id="kn-3",
        project_id=prj_payments.id,
        label="Environment Recreator Spec",
        category="tooling",
        details="Automated dev container and env spec generator for incoming team members to reproduce local environments.",
        owner="Synora Sentinel",
        confidence_score=0.98,
        verification_status="verified",
    )
    kn_4 = ExtractedKnowledge(
        id="kn-4",
        project_id=prj_payments.id,
        label="Continuity Handover Engine",
        category="process",
        details="AI-driven transition assistant creating structured exit dossiers and task continuity plans.",
        owner="Team Lead",
        confidence_score=0.96,
        verification_status="verified",
    )
    db.add_all([kn_1, kn_2, kn_3, kn_4])
    db.flush()

    # 9. Knowledge Relationships
    rel_01 = KnowledgeRelationship(
        id="rel-01",
        source_id=kn_1.id,
        target_id=kn_2.id,
        relation_type="DEPENDS_ON",
        confidence=0.90,
        metadata_tags={"direction": "upstream", "criticality": "high"},
    )
    rel_02 = KnowledgeRelationship(
        id="rel-02",
        source_id=kn_4.id,
        target_id=kn_1.id,
        relation_type="OWNS",
        confidence=0.95,
        metadata_tags={"verified_by": "Marcus Vance"},
    )
    db.add_all([rel_01, rel_02])

    # 10. Environment Snapshot
    env_snap = EnvironmentSnapshot(
        id="env-01",
        project_id=prj_payments.id,
        environment_name="Local Developer Quickstart",
        stack_type="python_fastapi_react_vite",
        blueprint_spec={
            "python_version": "3.12.6",
            "node_version": "26.13.0",
            "ports": {"backend": 8000, "frontend": 5173},
            "services": ["fastapi", "react-vite", "postgresql"],
        },
        powershell_quickstart="# Local PowerShell Quickstart\ncd backend; .venv\\Scripts\\python.exe run.py\ncd frontend; npm.cmd run dev",
        bash_quickstart="# Bash Quickstart\ncd backend && source .venv/bin/activate && python run.py\ncd frontend && npm run dev",
    )
    db.add(env_snap)

    # 11. Initial Seed Documents & Chunks (Module 1)
    doc_raft = Document(
        id="doc-raft-101",
        project_id=prj_payments.id,
        handover_id=ho_alex.id,
        uploaded_by_id=dev_alex.id,
        filename="raft_consensus_failover_spec.md",
        content_type="text/markdown",
        file_size=3450,
        file_hash="9a8f237b12093847e098df12348a7b65c43d21e0f98a7b6c5d4e3f2a1b0c9d8e",
        storage_path="projects/prj-pay-01/raft_consensus_failover_spec.md",
        processing_status="processed",
        raw_text="""# Distributed Consensus & Failover Architecture

## 1. Raft Leader Election & Heartbeat Timing
The payments transaction cluster uses Raft consensus with a 150ms heartbeat interval and a 300-500ms randomized election timeout.
In multi-region deployments (us-east-1 and us-west-2), cross-region network latency must remain under 120ms to prevent spurious leader re-elections.

## 2. Emergency Quorum Recovery Runbook
If network partition isolates two of three validator nodes:
1. Do not reboot healthy pods — this triggers split-brain log compaction.
2. Verify ingress routing table in AWS Route53 before forcing leader step-down.
3. Decrypt quorum recovery token in HashiCorp Vault namespace `/prod/settlement/tokens`.
4. Run `synora-raft-ctl --force-quorum-verify --region us-east-1`.

## 3. Database Replication & Ingress Routing
The transaction ledger is synchronized synchronously across two availability zones with asynchronous streaming to the disaster recovery region.
""",
        metadata_tags={
            "original_filename": "raft_consensus_failover_spec.md",
            "file_extension": ".md",
            "storage_backend": "local",
            "chunk_count": 2,
            "total_words": 154,
        },
    )
    db.add(doc_raft)
    db.flush()

    embedder = get_embedding_provider()
    chunk_1_text = "The payments transaction cluster uses Raft consensus with a 150ms heartbeat interval and a 300-500ms randomized election timeout. In multi-region deployments, cross-region latency must remain under 120ms to prevent spurious leader re-elections."
    chunk_2_text = "Emergency Quorum Recovery Runbook: If network partition isolates nodes, do not reboot healthy pods. Verify ingress routing table in Route53 before forcing leader step-down. Decrypt quorum recovery token in HashiCorp Vault namespace /prod/settlement/tokens."

    emb_1 = embedder.embed_text(chunk_1_text)
    chunk_1 = DocumentChunk(
        id="chk-raft-01",
        document_id=doc_raft.id,
        chunk_index=0,
        chunk_text=chunk_1_text,
        token_count=45,
        page_number=None,
        embedding_json=emb_1,
        embedding_vector=emb_1,
        metadata_tags={"source_filename": doc_raft.filename, "chunk_index": 0},
    )
    emb_2 = embedder.embed_text(chunk_2_text)
    chunk_2 = DocumentChunk(
        id="chk-raft-02",
        document_id=doc_raft.id,
        chunk_index=1,
        chunk_text=chunk_2_text,
        token_count=52,
        page_number=None,
        embedding_json=emb_2,
        embedding_vector=emb_2,
        metadata_tags={"source_filename": doc_raft.filename, "chunk_index": 1},
    )
    db.add_all([chunk_1, chunk_2])

    # 12. Initial Audit Log
    db.add(AuditLog(
        id="aud-init-01",
        user_id=admin.id,
        action="initialize_system",
        entity_type="system",
        entity_id="synora-core",
        details={"status": "database_seeded", "tables_initialized": 15},
    ))

    db.commit()


def init_db() -> None:
    """Create all tables and seed database if empty."""
    from sqlalchemy import text
    if not str(engine.url).startswith("sqlite"):
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                conn.commit()
        except Exception:
            pass

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized and seeded successfully.")
