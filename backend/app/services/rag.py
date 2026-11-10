import logging
import time
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.embeddings import (
    EmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)
from app.core.llm import LLMProvider, get_llm_provider
from app.models import Document, DocumentChunk, ExtractedKnowledge, Project
from app.schemas.common import (
    KnowledgeQueryRequest,
    KnowledgeQueryResponse,
    SourceCitation,
)

logger = logging.getLogger("synora.rag")


class RAGService:
    """
    Implements AI Knowledge Assistant & Grounded Vector Retrieval (Module 4).
    Features strict cross-project isolation, cosine similarity filtering,
    explicit uncertainty handling, and verifiable source citations.
    """

    def __init__(
        self,
        embedder: Optional[EmbeddingProvider] = None,
        llm: Optional[LLMProvider] = None,
    ):
        self.embedder = embedder or get_embedding_provider()
        self.llm = llm or get_llm_provider()

    def ensure_project_embeddings(self, db: Session, project_id: str) -> int:
        """
        Embeds any un-embedded chunks for documents belonging to this project.
        Returns the number of newly embedded chunks.
        """
        chunks_missing_emb = (
            db.query(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(Document.project_id == project_id)
            .filter(DocumentChunk.embedding_json.is_(None))
            .all()
        )

        if not chunks_missing_emb:
            return 0

        embedded_count = 0
        for chunk in chunks_missing_emb:
            vec = self.embedder.embed_text(chunk.chunk_text)
            chunk.embedding_json = vec
            chunk.embedding_vector = vec
            embedded_count += 1

        db.commit()
        logger.info(f"Generated embeddings for {embedded_count} chunks in project {project_id}.")
        return embedded_count

    def query(self, db: Session, payload: KnowledgeQueryRequest) -> KnowledgeQueryResponse:
        """
        Executes grounded RAG search and answer generation.
        """
        start_time = time.perf_counter()

        # 1. Project Verification & Cross-Project Boundary Check
        project = db.query(Project).filter(Project.id == payload.project_id).first()
        if not project:
            raise ValueError(f"Project '{payload.project_id}' not found.")

        # Ensure all project chunks have vector representations
        self.ensure_project_embeddings(db, project.id)

        # 2. Embed the Incoming Query
        query_text = payload.query.strip()
        if not query_text:
            raise ValueError("Query string cannot be empty.")

        query_vec = self.embedder.embed_text(query_text)

        # 3. Retrieve All Chunks for THIS Project (Cross-Project Data Isolation)
        project_chunks = (
            db.query(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(Document.project_id == project.id)
            .all()
        )

        if not project_chunks:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return KnowledgeQueryResponse(
                query=query_text,
                project_id=project.id,
                project_name=project.name,
                answer=f"No verified institutional documentation exists for this query in project '{project.name}'. (Project currently contains 0 ingested document chunks).",
                confidence=0.0,
                is_grounded=False,
                has_verified_knowledge=False,
                uncertainty_warning="Insufficient evidence: No project documents available to ground an answer.",
                citations=[],
                retrieved_chunk_count=0,
                processing_time_ms=elapsed_ms,
                answer_source="none",
            )

        # 4. Compute Vector Cosine Similarity
        scored_chunks: List[Dict[str, Any]] = []
        max_sim = 0.0

        for chunk, doc in project_chunks:
            chunk_vec = chunk.embedding_json
            if not chunk_vec:
                chunk_vec = self.embedder.embed_text(chunk.chunk_text)
                chunk.embedding_json = chunk_vec

            sim = cosine_similarity(query_vec, chunk_vec)
            if sim > max_sim:
                max_sim = sim

            scored_chunks.append({
                "chunk": chunk,
                "document": doc,
                "similarity": sim,
            })

        # Sort chunks by cosine similarity descending
        scored_chunks.sort(key=lambda x: x["similarity"], reverse=True)

        # 5. Filter by Similarity Threshold
        threshold = payload.similarity_threshold
        top_matches = [item for item in scored_chunks if item["similarity"] >= threshold][:payload.top_k]

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # 6. Honest Uncertainty / No Evidence Protocol
        if not top_matches:
            return KnowledgeQueryResponse(
                query=query_text,
                project_id=project.id,
                project_name=project.name,
                answer=(
                    f"No verified institutional documentation exists for this query in project '{project.name}'. "
                    f"(Highest similarity was {max_sim:.2f}, below the required confidence threshold of {threshold:.2f})."
                ),
                confidence=round(max_sim, 3),
                is_grounded=False,
                has_verified_knowledge=False,
                uncertainty_warning="Insufficient evidence: System refused to speculate or fabricate ungrounded operational facts.",
                citations=[],
                retrieved_chunk_count=0,
                processing_time_ms=elapsed_ms,
                answer_source="none",
            )

        # 7. Collect Evidence Context & Citations
        citations: List[SourceCitation] = []
        context_blocks: List[Dict[str, Any]] = []
        has_any_verified = False

        for match in top_matches:
            c: DocumentChunk = match["chunk"]
            d: Document = match["document"]
            sim_score = round(match["similarity"], 3)

            # Check if this chunk is linked to verified ExtractedKnowledge
            linked_extractions = (
                db.query(ExtractedKnowledge)
                .filter(ExtractedKnowledge.chunk_id == c.id)
                .all()
            )
            
            # Determine chunk verification status
            if linked_extractions:
                is_verified = any(e.verification_status in ("verified", "modified") for e in linked_extractions)
                status_str = "verified" if is_verified else "unverified"
            else:
                status_str = "verified" if d.processing_status == "processed" else "unverified"

            if status_str == "verified":
                has_any_verified = True

            snippet = c.chunk_text.strip()
            if len(snippet) > 220:
                snippet = snippet[:220] + "..."

            citation = SourceCitation(
                document_id=d.id,
                document_name=d.filename,
                chunk_id=c.id,
                chunk_index=c.chunk_index,
                page_number=c.page_number,
                similarity_score=sim_score,
                verification_status=status_str,
                snippet=snippet,
            )
            citations.append(citation)

            context_blocks.append({
                "chunk_text": c.chunk_text,
                "document_name": d.filename,
                "chunk_index": c.chunk_index,
                "similarity": sim_score,
                "verification_status": status_str,
            })

        # 8. Synthesize Grounded Answer via LLM Provider
        generate_with_status = getattr(self.llm, "generate_rag_answer_with_status", None)
        if generate_with_status:
            answer_text, answer_source = generate_with_status(
                query=query_text, context_chunks=context_blocks, project_name=project.name
            )
        else:
            answer_text = self.llm.generate_rag_answer(
                query=query_text, context_chunks=context_blocks, project_name=project.name
            )
            provider_info = self.llm.get_provider_info()
            answer_source = "deterministic_fallback" if provider_info.get("is_mock") else "unknown"

        avg_confidence = round(sum(c.similarity_score for c in citations) / len(citations), 3)

        uncertainty_msg: Optional[str] = None
        if not has_any_verified:
            uncertainty_msg = "Note: Underlying source chunks contain extractions that have not yet been approved by an engineering manager."

        return KnowledgeQueryResponse(
            query=query_text,
            project_id=project.id,
            project_name=project.name,
            answer=answer_text,
            confidence=avg_confidence,
            is_grounded=True,
            has_verified_knowledge=has_any_verified,
            uncertainty_warning=uncertainty_msg,
            citations=citations,
            retrieved_chunk_count=len(citations),
            processing_time_ms=elapsed_ms,
            answer_source=answer_source,
        )

