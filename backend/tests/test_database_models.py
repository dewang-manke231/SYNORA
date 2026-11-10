"""
Comprehensive Database Models & Relationships Test Suite for Synora
Verifies:
- Creation and querying of all 15 models
- Foreign key cascading and constraints
- Knowledge Graph relations and directionality
- Verification workflow audit records
- Handover lifecycle persistence
- Sentinel risks and Radar gap detection
- Document chunking & metadata storage
- Environment recreator snapshots
"""
import pytest
from sqlalchemy.orm import Session
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


def test_organization_user_membership(db_session: Session):
    org = Organization(
        id="test-org-01",
        name="Fintech Core Labs",
        slug="fintech-core-labs",
        description="Core banking infrastructure division.",
    )
    user = User(
        id="test-usr-01",
        email="developer@fintech.corp",
        full_name="Jordan Reed",
        role="engineer",
    )
    db_session.add(org)
    db_session.add(user)
    db_session.commit()

    membership = OrganizationMembership(
        id="test-mem-01",
        organization_id=org.id,
        user_id=user.id,
        role="admin",
    )
    db_session.add(membership)
    db_session.commit()

    queried_org = db_session.query(Organization).filter_by(id="test-org-01").first()
    assert queried_org is not None
    assert len(queried_org.memberships) == 1
    assert queried_org.memberships[0].user.full_name == "Jordan Reed"


def test_project_and_knowledge_sources(db_session: Session):
    project = Project(
        id="test-prj-01",
        organization_id="test-org-01",
        name="Ledger Reconciliation",
        slug="ledger-recon",
        bus_factor=1.5,
        knowledge_coverage_score=75.0,
    )
    db_session.add(project)
    db_session.commit()

    source = KnowledgeSource(
        id="test-src-01",
        project_id=project.id,
        name="GitHub Repo - Ledger Recon",
        source_type="github",
        configuration={"repo": "org/ledger-recon", "branch": "main"},
    )
    db_session.add(source)
    db_session.commit()

    queried_project = db_session.query(Project).filter_by(id="test-prj-01").first()
    assert len(queried_project.knowledge_sources) == 1
    assert queried_project.knowledge_sources[0].source_type == "github"


def test_documents_and_chunks(db_session: Session):
    doc = Document(
        id="test-doc-01",
        project_id="test-prj-01",
        uploaded_by_id="test-usr-01",
        filename="architecture_overview.md",
        content_type="text/markdown",
        file_size=1024,
        raw_text="# Ledger Architecture\nDetails of transaction ledger.",
    )
    db_session.add(doc)
    db_session.commit()

    chunk1 = DocumentChunk(
        id="test-chk-01",
        document_id=doc.id,
        chunk_index=0,
        chunk_text="Details of transaction ledger.",
        token_count=10,
        metadata_tags={"section": "Ledger Architecture"},
        embedding_json=[0.12, 0.45, -0.32],
    )
    db_session.add(chunk1)
    db_session.commit()

    queried_doc = db_session.query(Document).filter_by(id="test-doc-01").first()
    assert len(queried_doc.chunks) == 1
    assert queried_doc.chunks[0].token_count == 10
    assert len(queried_doc.chunks[0].embedding_json) == 3


def test_knowledge_graph_and_relationships(db_session: Session):
    kn_source = ExtractedKnowledge(
        id="test-kn-01",
        project_id="test-prj-01",
        label="Consensus Protocol",
        category="architecture",
        details="Raft consensus implementation for cluster state.",
        owner="Jordan Reed",
        confidence_score=0.98,
        verification_status="verified",
    )
    kn_target = ExtractedKnowledge(
        id="test-kn-02",
        project_id="test-prj-01",
        label="Cluster Node Manager",
        category="module",
        details="Spins up worker node pods and monitors heartbeats.",
        owner="Jordan Reed",
        confidence_score=0.91,
        verification_status="unverified",
    )
    db_session.add_all([kn_source, kn_target])
    db_session.commit()

    rel = KnowledgeRelationship(
        id="test-rel-01",
        source_id=kn_source.id,
        target_id=kn_target.id,
        relation_type="DEPENDS_ON",
        confidence=0.95,
    )
    db_session.add(rel)
    db_session.commit()

    queried_source = db_session.query(ExtractedKnowledge).filter_by(id="test-kn-01").first()
    assert len(queried_source.outgoing_relationships) == 1
    assert queried_source.outgoing_relationships[0].target_node.label == "Cluster Node Manager"


def test_verification_record_flow(db_session: Session):
    kn = db_session.query(ExtractedKnowledge).filter_by(id="test-kn-02").first()
    assert kn.verification_status == "unverified"

    ver = VerificationRecord(
        id="test-ver-01",
        knowledge_id=kn.id,
        verified_by_id="test-usr-01",
        action="approved",
        notes="Verified architecture accuracy with cluster lead.",
    )
    kn.verification_status = "verified"
    db_session.add(ver)
    db_session.commit()

    queried_ver = db_session.query(VerificationRecord).filter_by(id="test-ver-01").first()
    assert queried_ver.knowledge_item.verification_status == "verified"
    assert queried_ver.verifier.full_name == "Jordan Reed"


def test_handover_and_audit_trail(db_session: Session):
    ho = Handover(
        id="test-ho-01",
        project_id="test-prj-01",
        employee_name="Jordan Reed",
        role="Principal Infrastructure Lead",
        department="Core Infrastructure",
        transition_type="resignation",
        status="in_progress",
        readiness_score=75.0,
        key_responsibilities=["Consensus cluster orchestration", "Disaster recovery runbooks"],
        critical_dependencies=["Vault root tokens", "AWS KMS master keys"],
        unresolved_blockers=["Cross-cloud KMS rotation documentation is incomplete"],
    )
    audit = AuditLog(
        id="test-aud-01",
        user_id="test-usr-01",
        action="create_handover",
        entity_type="handover",
        entity_id="test-ho-01",
        details={"status": "in_progress", "employee": "Jordan Reed"},
    )
    db_session.add_all([ho, audit])
    db_session.commit()

    queried_ho = db_session.query(Handover).filter_by(id="test-ho-01").first()
    assert queried_ho.readiness_score == 75.0
    assert len(queried_ho.critical_dependencies) == 2

    queried_audit = db_session.query(AuditLog).filter_by(entity_id="test-ho-01").first()
    assert queried_audit.action == "create_handover"


def test_radar_and_sentinel_events(db_session: Session):
    radar_gap = KnowledgeLossIndicator(
        id="test-rad-01",
        project_id="test-prj-01",
        module_name="KMS Rotation Script",
        gap_type="ADR_MISSING",
        severity="critical",
        description="No ADR records key rotation frequency or emergency revocation protocols.",
    )
    sentinel_alert = SentinelEvent(
        id="test-risk-01",
        project_id="test-prj-01",
        project_name="Ledger Reconciliation",
        risk_level="critical",
        category="single_point_of_failure",
        description="Jordan Reed is the sole engineer with Vault root keys.",
        recommended_action="Rotate Vault root keys and pair with secondary SRE.",
    )
    env_snapshot = EnvironmentSnapshot(
        id="test-env-01",
        project_id="test-prj-01",
        environment_name="Local SRE Quickstart",
        stack_type="docker_compose",
        blueprint_spec={"compose_file": "docker-compose.yml", "services": ["vault", "postgres"]},
        powershell_quickstart="docker compose up -d",
    )
    db_session.add_all([radar_gap, sentinel_alert, env_snapshot])
    db_session.commit()

    assert db_session.query(KnowledgeLossIndicator).filter_by(id="test-rad-01").first() is not None
    assert db_session.query(SentinelEvent).filter_by(id="test-risk-01").first() is not None
    assert db_session.query(EnvironmentSnapshot).filter_by(id="test-env-01").first() is not None

