from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Document, DocumentChunk, Handover, User
from app.schemas.common import (
    DocumentItemResponse,
    DocumentDetailResponse,
    DocumentChunkResponse,
    DocumentDeleteResponse,
    DocumentDownloadResponse,
)
from app.services.ingestion import (
    IngestionService,
    UnsupportedFileError,
    FileSizeLimitError,
    DuplicateDocumentError,
    IngestionError,
)
from app.services.storage import get_storage_provider, SupabaseStorageProvider
from app.core.security import (
    get_current_user,
    get_accessible_project_ids,
    verify_document_organization_access,
    verify_project_organization_access,
    verify_handover_organization_access,
)

router = APIRouter()
ingestion_service = IngestionService()
storage_provider = get_storage_provider()


def _to_document_item_response(doc: Document, db: Session) -> DocumentItemResponse:
    chunk_count = (
        doc.metadata_tags.get("chunk_count")
        if doc.metadata_tags and "chunk_count" in doc.metadata_tags
        else db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).count()
    )
    return DocumentItemResponse(
        id=doc.id,
        project_id=doc.project_id,
        handover_id=doc.handover_id,
        filename=doc.filename,
        content_type=doc.content_type,
        file_size=doc.file_size,
        file_hash=doc.file_hash,
        storage_path=doc.storage_path,
        processing_status=doc.processing_status,
        error_message=doc.error_message,
        chunk_count=chunk_count,
        metadata_tags=doc.metadata_tags,
        uploaded_at=doc.uploaded_at,
    )


def _to_document_detail_response(doc: Document, db: Session) -> DocumentDetailResponse:
    chunk_count = (
        doc.metadata_tags.get("chunk_count")
        if doc.metadata_tags and "chunk_count" in doc.metadata_tags
        else db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).count()
    )
    return DocumentDetailResponse(
        id=doc.id,
        project_id=doc.project_id,
        handover_id=doc.handover_id,
        filename=doc.filename,
        content_type=doc.content_type,
        file_size=doc.file_size,
        file_hash=doc.file_hash,
        storage_path=doc.storage_path,
        processing_status=doc.processing_status,
        error_message=doc.error_message,
        chunk_count=chunk_count,
        metadata_tags=doc.metadata_tags,
        uploaded_at=doc.uploaded_at,
        raw_text=doc.raw_text or "",
    )


@router.post("/upload", response_model=DocumentDetailResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    handover_id: Optional[str] = Form(None),
    uploader_name: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Uploads a document (PDF, Markdown, or TXT), validates extension/MIME/size,
    stores safely in persistent storage (Supabase Storage or Local), extracts plain text,
    and persists structured chunks with SHA-256 deduplication.
    """
    file_bytes = await file.read()
    try:
        ingestion_service.validate_file(file.filename or "", file.content_type or "application/octet-stream", file_bytes)
    except (UnsupportedFileError, FileSizeLimitError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if project_id and current_user:
        verify_project_organization_access(project_id, current_user, db)
    elif handover_id:
        verify_handover_organization_access(handover_id, current_user, db)
    else:
        raise HTTPException(status_code=422, detail="project_id or handover_id is required for document upload.")

    try:
        actor = current_user.full_name
        doc = ingestion_service.process_and_store_document(
            db=db,
            file_bytes=file_bytes,
            filename=file.filename or "unnamed_document.txt",
            content_type=file.content_type or "application/octet-stream",
            project_id=project_id,
            handover_id=handover_id,
            uploaded_by_id=actor,
        )
        return _to_document_detail_response(doc, db)

    except UnsupportedFileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except FileSizeLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except DuplicateDocumentError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(e),
                "existing_document_id": e.existing_document_id,
            },
        )
    except IngestionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during document ingestion: {str(e)}",
        )


@router.get("/", response_model=List[DocumentItemResponse])
def list_documents(
    project_id: Optional[str] = None,
    handover_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lists ingested documents with optional filtering and organization-level isolation.
    """
    if project_id and current_user:
        verify_project_organization_access(project_id, current_user, db)

    query = db.query(Document)
    allowed_projects = get_accessible_project_ids(current_user, db)
    if project_id is None and allowed_projects is not None:
        query = query.filter(Document.project_id.in_(allowed_projects)) if allowed_projects else query.filter(Document.project_id == "__no_access__")
    if project_id:
        query = query.filter(Document.project_id == project_id)
    if handover_id:
        query = query.filter(Document.handover_id == handover_id)
    if status_filter:
        query = query.filter(Document.processing_status == status_filter)

    documents = query.order_by(Document.uploaded_at.desc()).all()
    return [_to_document_item_response(doc, db) for doc in documents]


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves complete metadata and extracted text for a specific document.
    Enforces organization-level access boundaries.
    """
    if current_user:
        doc = verify_document_organization_access(document_id, current_user, db)
    else:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID '{document_id}' not found.",
            )
    return _to_document_detail_response(doc, db)


@router.get("/{document_id}/download", response_model=DocumentDownloadResponse)
def get_document_download_url(
    document_id: str,
    expires_in: int = 3600,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generates a secure, short-lived signed download URL for authorized users.
    Never exposes service-role keys to the frontend.
    """
    if current_user:
        doc = verify_document_organization_access(document_id, current_user, db)
    else:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID '{document_id}' not found.",
            )

    storage = get_storage_provider()
    is_supabase = isinstance(storage, SupabaseStorageProvider)
    storage_backend = "supabase" if is_supabase else "local"

    try:
        signed_url = storage.create_signed_url(doc.storage_path or "", expires_in=expires_in)
    except Exception as e:
        # Fallback to local streaming route if signed URL cannot be generated
        signed_url = f"/api/v1/documents/{doc.id}/stream"

    return DocumentDownloadResponse(
        document_id=doc.id,
        filename=doc.filename,
        storage_backend=storage_backend,
        download_url=signed_url,
        expires_in=expires_in,
        file_size=doc.file_size,
        file_hash=doc.file_hash,
    )


@router.get("/{document_id}/stream")
def stream_document_content(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Directly streams document binary content for authorized users.
    """
    if current_user:
        doc = verify_document_organization_access(document_id, current_user, db)
    else:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID '{document_id}' not found.",
            )

    storage = get_storage_provider()
    try:
        content_bytes = storage.read(doc.storage_path or "")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to read file from storage: {str(e)}",
        )

    return Response(
        content=content_bytes,
        media_type=doc.content_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )


@router.get("/{document_id}/chunks", response_model=List[DocumentChunkResponse])
def get_document_chunks(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves all ordered chunks for a document.
    """
    if current_user:
        verify_document_organization_access(document_id, current_user, db)
    else:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID '{document_id}' not found.",
            )

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    return chunks


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(
    document_id: str,
    actor_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Deletes the document from persistent storage (Supabase or Local) and purges cascaded chunks.
    Enforces organization-level access authorization.
    """
    if current_user:
        verify_document_organization_access(document_id, current_user, db)

    actor = actor_name or current_user.full_name
    success = ingestion_service.delete_document(db, document_id, actor_id=actor)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )
    return DocumentDeleteResponse(
        success=True,
        deleted_id=document_id,
        message=f"Document '{document_id}' and all associated chunks were successfully deleted.",
    )
