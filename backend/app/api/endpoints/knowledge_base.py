"""
Knowledge Base API Endpoints — Document upload, management, and RAG search

Provides REST endpoints for managing the RAG knowledge base:
  - Upload documents (PDF, DOCX, TXT, MD)
  - List and manage uploaded documents
  - Semantic search across the knowledge base
  - Knowledge base status and health

Requires: Group Admin for upload/delete, any authenticated user for search/list.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_tenant_admin
from app.db.kb_session import get_kb_db
from app.models.user import User
from app.services.knowledge_base_service import KnowledgeBaseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SearchRequest(BaseModel):
    """Semantic search query."""
    query: str = Field(..., min_length=1, max_length=2000, description="Search query")
    top_k: int = Field(5, ge=1, le=20, description="Number of results")
    category: Optional[str] = Field(None, description="Filter by document category")


class SearchResult(BaseModel):
    """A single search result."""
    chunk_id: int
    document_id: int
    document_title: str
    content: str
    chunk_index: int
    page_number: Optional[int]
    score: float
    metadata: Optional[Dict[str, Any]]


class SearchResponse(BaseModel):
    """Search response with results."""
    query: str
    results: List[SearchResult]
    total: int


# ============================================================================
# Document Upload
# ============================================================================

@router.post("/documents", tags=["knowledge-base"])
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # Comma-separated tags
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_kb_db),
) -> Dict[str, Any]:
    """Upload and index a document for RAG.

    Supports PDF, DOCX, TXT, and MD files. The document is parsed, chunked,
    embedded, and stored in pgvector for similarity search.

    Requires: Group Admin
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Validate file type
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("pdf", "docx", "txt", "md", "csv"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{ext}. Supported: pdf, docx, txt, md, csv"
        )

    # Read file content
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # Parse tags
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    service = KnowledgeBaseService(db, current_user.tenant_id)

    try:
        result = await service.ingest_document(
            file_bytes=file_bytes,
            filename=file.filename,
            title=title,
            category=category,
            description=description,
            tags=tag_list,
            uploaded_by=current_user.id,
        )
        return {"status": "success", "document": result}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Document upload failed: {e}")
        raise HTTPException(status_code=500, detail="Document processing failed")


# ============================================================================
# Document Management
# ============================================================================

@router.get("/documents", tags=["knowledge-base"])
async def list_documents(
    status: Optional[str] = Query(None, description="Filter by status"),
    category: Optional[str] = Query(None, description="Filter by category"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_kb_db),
) -> Dict[str, Any]:
    """List all documents in the knowledge base.

    Requires: Any authenticated user
    """
    service = KnowledgeBaseService(db, current_user.tenant_id)
    documents = await service.list_documents(status=status, category=category)
    return {"documents": documents, "total": len(documents)}


@router.get("/documents/{document_id}", tags=["knowledge-base"])
async def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_kb_db),
) -> Dict[str, Any]:
    """Get details of a specific document.

    Requires: Any authenticated user
    """
    service = KnowledgeBaseService(db, current_user.tenant_id)
    doc = await service.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"document": doc}


@router.delete("/documents/{document_id}", tags=["knowledge-base"])
async def delete_document(
    document_id: int,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_kb_db),
) -> Dict[str, Any]:
    """Delete a document and all its chunks.

    Requires: Group Admin
    """
    service = KnowledgeBaseService(db, current_user.tenant_id)
    deleted = await service.delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted", "document_id": document_id}


# ============================================================================
# RAG Search
# ============================================================================

@router.post("/search", response_model=SearchResponse, tags=["knowledge-base"])
async def search_knowledge_base(
    request: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_kb_db),
) -> SearchResponse:
    """Semantic search across the knowledge base.

    Embeds the query and finds the most similar document chunks
    using pgvector cosine distance.

    Requires: Any authenticated user
    """
    service = KnowledgeBaseService(db, current_user.tenant_id)

    try:
        results = await service.search(
            query=request.query,
            top_k=request.top_k,
            category=request.category,
        )
        return SearchResponse(
            query=request.query,
            results=[
                SearchResult(
                    chunk_id=r.chunk_id,
                    document_id=r.document_id,
                    document_title=r.document_title,
                    content=r.content,
                    chunk_index=r.chunk_index,
                    page_number=r.page_number,
                    score=r.score,
                    metadata=r.metadata,
                )
                for r in results
            ],
            total=len(results),
        )

    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail="Search failed")


# ============================================================================
# Status
# ============================================================================

@router.get("/status", tags=["knowledge-base"])
async def get_knowledge_base_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_kb_db),
) -> Dict[str, Any]:
    """Get knowledge base status and statistics.

    Includes document counts, embedding service health, and configuration.

    Requires: Any authenticated user
    """
    service = KnowledgeBaseService(db, current_user.tenant_id)
    return await service.get_status()
