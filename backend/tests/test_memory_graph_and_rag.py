import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.embeddings import (
    DeterministicMockEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)
from app.main import app
from app.models import (
    Document,
    DocumentChunk,
    ExtractedKnowledge,
    KnowledgeRelationship,
    Project,
)
from app.core.security import create_access_token

MANAGER_HEADERS = {"Authorization": f"Bearer {create_access_token({'sub': 'usr-mgr-01', 'email': 'marcus.vance@acme.corp', 'role': 'manager', 'org_id': 'org-acme-01'})}"}


@pytest.fixture(scope="module", autouse=True)
def setup_seed_data():
    """Ensure baseline enterprise seed records exist for graph and RAG tests."""
    db = SessionLocal()
    try:
        # 1. Ensure Projects exist
        prj = db.query(Project).filter(Project.id == "prj-pay-01").first()
        if not prj:
            prj = Project(
                id="prj-pay-01",
                name="Payments & Settlement Engine",
                slug="payments-settlement",
                description="Distributed multi-region transaction processing engine running Raft consensus.",
                bus_factor=1.0,
                knowledge_coverage_score=68.5,
            )
            db.add(prj)

        prj_auth = db.query(Project).filter(Project.id == "prj-auth-01").first()
        if not prj_auth:
            prj_auth = Project(
                id="prj-auth-01",
                name="Auth & Identity Platform",
                slug="auth-identity",
                description="OAuth2/OIDC centralized identity service and RBAC token validator.",
                bus_factor=2.0,
                knowledge_coverage_score=91.0,
            )
            db.add(prj_auth)
        db.flush()

        # 2. Ensure Document and Chunks exist for prj-pay-01
        doc = db.query(Document).filter(Document.id == "doc-raft-101").first()
        if not doc:
            doc = Document(
                id="doc-raft-101",
                project_id="prj-pay-01",
                filename="raft_consensus_failover_spec.md",
                content_type="text/markdown",
                file_size=3450,
                file_hash="9a8f237b12093847e098df12348a7b65c43d21e0f98a7b6c5d4e3f2a1b0c9d8e",
                processing_status="processed",
                raw_text="The payments transaction cluster uses Raft consensus with a 150ms heartbeat interval and a 300-500ms randomized election timeout.",
                metadata_tags={"source_filename": "raft_consensus_failover_spec.md", "chunk_count": 2},
            )
            db.add(doc)
            db.flush()

        embedder = get_embedding_provider()
        chk1 = db.query(DocumentChunk).filter(DocumentChunk.id == "chk-raft-01").first()
        txt1 = "The payments transaction cluster uses Raft consensus with a 150ms heartbeat interval and a 300-500ms randomized election timeout. In multi-region deployments, cross-region latency must remain under 120ms to prevent spurious leader re-elections."
        if not chk1:
            chk1 = DocumentChunk(
                id="chk-raft-01",
                document_id=doc.id,
                chunk_index=0,
                chunk_text=txt1,
                token_count=45,
                embedding_json=embedder.embed_text(txt1),
                metadata_tags={"source_filename": doc.filename, "chunk_index": 0},
            )
            db.add(chk1)
        else:
            chk1.embedding_json = embedder.embed_text(txt1)

        chk2 = db.query(DocumentChunk).filter(DocumentChunk.id == "chk-raft-02").first()
        txt2 = "Emergency Quorum Recovery Runbook: If network partition isolates nodes, do not reboot healthy pods. Verify ingress routing table in Route53 before forcing leader step-down. Decrypt quorum recovery token in HashiCorp Vault namespace /prod/settlement/tokens."
        if not chk2:
            chk2 = DocumentChunk(
                id="chk-raft-02",
                document_id=doc.id,
                chunk_index=1,
                chunk_text=txt2,
                token_count=52,
                embedding_json=embedder.embed_text(txt2),
                metadata_tags={"source_filename": doc.filename, "chunk_index": 1},
            )
            db.add(chk2)
        else:
            chk2.embedding_json = embedder.embed_text(txt2)

        # 3. Ensure knowledge items and relationship exist
        kn1 = db.query(ExtractedKnowledge).filter(ExtractedKnowledge.id == "kn-raft-01").first()
        if not kn1:
            kn1 = ExtractedKnowledge(
                id="kn-raft-01",
                project_id="prj-pay-01",
                document_id=doc.id,
                chunk_id=chk1.id,
                label="Raft Consensus Failover Protocol",
                category="architecture",
                details="Core payments failover consensus mechanism requiring 150ms heartbeat interval.",
                owner="Alex Mercer",
                confidence_score=0.95,
                verification_status="verified",
                source_quote="The payments transaction cluster uses Raft consensus with a 150ms heartbeat interval",
            )
            db.add(kn1)

        kn2 = db.query(ExtractedKnowledge).filter(ExtractedKnowledge.id == "kn-raft-02").first()
        if not kn2:
            kn2 = ExtractedKnowledge(
                id="kn-raft-02",
                project_id="prj-pay-01",
                document_id=doc.id,
                chunk_id=chk2.id,
                label="Multi-Region Quorum Recovery Runbook",
                category="instruction",
                details="Emergency quorum restoration procedure using HashiCorp Vault recovery tokens.",
                owner="Alex Mercer",
                confidence_score=0.90,
                verification_status="verified",
                source_quote="Emergency Quorum Recovery Runbook: If network partition isolates nodes",
            )
            db.add(kn2)
        db.flush()

        rel = db.query(KnowledgeRelationship).filter(KnowledgeRelationship.id == "rel-raft-01").first()
        if not rel:
            rel = KnowledgeRelationship(
                id="rel-raft-01",
                source_id="kn-raft-01",
                target_id="kn-raft-02",
                relation_type="DEPENDS_ON",
                confidence=0.92,
                metadata_tags={"type": "architectural_dependency"},
            )
            db.add(rel)

        db.commit()
    finally:
        db.close()


def test_graph_retrieval_and_structure():
    """Verifies GET /api/v1/knowledge/graph returns valid nodes and grounded edges."""
    with TestClient(app, headers=MANAGER_HEADERS) as client:
        resp = client.get("/api/v1/knowledge/graph")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert "nodes" in data
        assert "edges" in data
        assert data["total_nodes"] > 0
        assert data["total_edges"] > 0
        assert data["verified_nodes"] >= 0

        # Verify node fields
        node_ids = {n["id"] for n in data["nodes"]}
        node_types = {n["node_type"] for n in data["nodes"]}
        assert "document" in node_types or "decision" in node_types or "task" in node_types

        # Verify no dangling edges
        for edge in data["edges"]:
            assert edge["source"] in node_ids, f"Edge source '{edge['source']}' missing in nodes"
            assert edge["target"] in node_ids, f"Edge target '{edge['target']}' missing in nodes"
            assert edge["relation_type"] in (
                "DEPENDS_ON",
                "IMPLEMENTS",
                "MAINTAINS",
                "DOCUMENTED_IN",
                "BLOCKED_BY",
                "OWNS",
                "INTERACTS_WITH",
            )


def test_graph_project_filtering():
    """Verifies that project filtering properly scopes nodes and edges."""
    with TestClient(app, headers=MANAGER_HEADERS) as client:
        # Filter for Payments Engine
        resp = client.get("/api/v1/knowledge/graph?project_id=prj-pay-01")
        assert resp.status_code == 200
        pay_data = resp.json()
        assert pay_data["project_name"] == "Payments & Settlement Engine"
        assert pay_data["project_id"] == "prj-pay-01"

        # All nodes must belong to prj-pay-01 or be shared owners
        for node in pay_data["nodes"]:
            if node["node_type"] != "owner" and node["project_id"]:
                assert node["project_id"] == "prj-pay-01"

        # Non-existent project returns 404
        bad_resp = client.get("/api/v1/knowledge/graph?project_id=non-existent-prj")
        assert bad_resp.status_code == 404


def test_graph_source_evidence_relationships():
    """Verifies that graph relationships reflect actual DB records and document links without invention."""
    with TestClient(app, headers=MANAGER_HEADERS) as client:
        resp = client.get("/api/v1/knowledge/graph?project_id=prj-pay-01")
        assert resp.status_code == 200
        data = resp.json()

        relation_types = {e["relation_type"] for e in data["edges"]}
        assert len(relation_types) > 0

        # Check documented_in edges link from extracted items to document
        doc_edges = [e for e in data["edges"] if e["relation_type"] == "DOCUMENTED_IN"]
        for de in doc_edges:
            tgt_node = next(n for n in data["nodes"] if n["id"] == de["target"])
            assert tgt_node["node_type"] == "document"


def test_vector_embedding_provider_deterministic():
    """Tests the deterministic mock vectorizer mathematical properties."""
    embedder = DeterministicMockEmbeddingProvider(dimension=64)
    assert embedder.dimension == 64

    # Vector normalization check
    v1 = embedder.embed_text("Raft consensus with 150ms heartbeat interval and election timeout.")
    assert len(v1) == 64
    norm1 = sum(x * x for x in v1)
    assert pytest.approx(norm1, abs=1e-3) == 1.0

    # Semantic similarity check: related texts
    v2 = embedder.embed_text("Heartbeat interval in Raft consensus cluster failover timeout.")
    sim_related = cosine_similarity(v1, v2)
    assert sim_related >= 0.65, f"Expected similarity >= 0.65 for related texts, got {sim_related}"

    # Semantic divergence check: completely unrelated text
    v_unrelated = embedder.embed_text("Employee travel mileage expense reimbursement policy for marketing.")
    sim_unrelated = cosine_similarity(v1, v_unrelated)
    assert sim_unrelated < 0.40, f"Expected similarity < 0.40 for unrelated texts, got {sim_unrelated}"


def test_rag_query_grounded_with_citations():
    """Verifies POST /api/v1/knowledge/query returns grounded answers and citations when evidence exists."""
    with TestClient(app, headers=MANAGER_HEADERS) as client:
        payload = {
            "project_id": "prj-pay-01",
            "query": "What is the Raft consensus heartbeat interval?",
            "similarity_threshold": 0.65,
            "top_k": 3,
        }
        resp = client.post("/api/v1/knowledge/query", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["is_grounded"] is True
        assert data["project_id"] == "prj-pay-01"
        assert len(data["citations"]) >= 1
        assert data["confidence"] >= 0.65

        # Check citation details
        top_cit = data["citations"][0]
        assert top_cit["document_name"] == "raft_consensus_failover_spec.md"
        assert top_cit["chunk_id"] == "chk-raft-01"
        assert top_cit["similarity_score"] >= 0.65
        assert "heartbeat" in top_cit["snippet"].lower() or "raft" in top_cit["snippet"].lower()

        # Check that answer mentions the heartbeat or raft consensus
        assert "heartbeat" in data["answer"].lower() or "150ms" in data["answer"].lower() or "raft" in data["answer"].lower()


def test_rag_query_no_evidence_uncertainty():
    """Verifies POST /api/v1/knowledge/query declares honest uncertainty when no evidence exists."""
    with TestClient(app, headers=MANAGER_HEADERS) as client:
        payload = {
            "project_id": "prj-pay-01",
            "query": "What are the quantum cryptographic teleportation protocols for orbital satellites?",
            "similarity_threshold": 0.65,
            "top_k": 3,
        }
        resp = client.post("/api/v1/knowledge/query", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Uncertainty requirements
        assert data["is_grounded"] is False
        assert len(data["citations"]) == 0
        assert data["uncertainty_warning"] is not None
        assert "No verified institutional documentation exists" in data["answer"]


def test_rag_cross_project_isolation():
    """Verifies that queries in project B cannot retrieve chunks from project A."""
    with TestClient(app, headers=MANAGER_HEADERS) as client:
        # Querying Auth Platform for Raft consensus (which only exists in Payments)
        payload = {
            "project_id": "prj-auth-01",
            "query": "What is the Raft consensus heartbeat interval in payments?",
            "similarity_threshold": 0.65,
            "top_k": 3,
        }
        resp = client.post("/api/v1/knowledge/query", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Must NOT return Payments chunks or citations!
        assert data["is_grounded"] is False
        assert len(data["citations"]) == 0
        for cit in data["citations"]:
            assert "raft" not in cit["document_name"].lower()


def test_llm_and_embedding_status_reporting():
    """Verifies that LLM and embedding connectivity statuses are reported accurately."""
    with TestClient(app, headers=MANAGER_HEADERS) as client:
        llm_resp = client.get("/api/v1/knowledge/llm-status")
        assert llm_resp.status_code == 200
        llm_data = llm_resp.json()
        assert "configured" in llm_data
        assert "provider" in llm_data

        emb_resp = client.get("/api/v1/knowledge/embedding-status")
        assert emb_resp.status_code == 200
        emb_data = emb_resp.json()
        assert "dimension" in emb_data
        assert "configured" in emb_data
        assert "provider" in emb_data
        assert emb_data["dimension"] in (64, 768, 1536, 3072)
