"""
Knowledge Base Models — Document Storage and Vector Embeddings for RAG

ORM models for managing uploaded documents and their chunked embeddings
used by the RAG (Retrieval-Augmented Generation) pipeline.

These models use a separate declarative Base (KBBase) so they can live
in an independent pgvector database without interfering with the main
application metadata.

Tables:
  - kb_documents: Uploaded documents (PDF, DOCX, TXT)
  - kb_chunks: Document chunks with pgvector embeddings for similarity search
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    Text, JSON, ForeignKey, Index,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    # Fallback for environments without pgvector installed
    Vector = None

# Separate Base — KB tables live in their own pgvector database
KBBase = declarative_base()


# ============================================================================
# Documents
# ============================================================================

class KBDocument(KBBase):
    """Uploaded document in the knowledge base.

    Stores metadata about uploaded files. The actual content is chunked
    and stored in kb_chunks with vector embeddings for retrieval.

    Note: group_id and uploaded_by are plain integers (no FK to main DB).
    Association is enforced at the application level, not the database level.
    """
    __tablename__ = "kb_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, nullable=False)  # Application-level ref to groups.id
    uploaded_by = Column(Integer, nullable=True)  # Application-level ref to users.id

    # Document metadata
    title = Column(String(500), nullable=False)
    filename = Column(String(500), nullable=False)
    file_type = Column(String(20), nullable=False)  # pdf, docx, txt, md
    file_size = Column(Integer, nullable=True)  # bytes
    page_count = Column(Integer, nullable=True)

    # Processing status
    status = Column(String(20), nullable=False, default="pending")  # pending, processing, indexed, failed
    error_message = Column(Text, nullable=True)
    chunk_count = Column(Integer, nullable=False, default=0)

    # Embedding metadata
    embedding_model = Column(String(200), nullable=True)
    embedding_dimensions = Column(Integer, nullable=True)

    # Optional categorization
    category = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)  # ["Q3", "2026", "financial"]

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships (within KB database only)
    chunks = relationship("KBChunk", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_kb_doc_group", "group_id"),
        Index("idx_kb_doc_status", "status"),
        Index("idx_kb_doc_category", "category"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "uploaded_by": self.uploaded_by,
            "title": self.title,
            "filename": self.filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "page_count": self.page_count,
            "status": self.status,
            "error_message": self.error_message,
            "chunk_count": self.chunk_count,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": self.embedding_dimensions,
            "category": self.category,
            "description": self.description,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ============================================================================
# Document Chunks with Vector Embeddings
# ============================================================================

class KBChunk(KBBase):
    """Document chunk with vector embedding for similarity search.

    Each document is split into overlapping chunks. Each chunk stores its
    text content and a pgvector embedding for cosine similarity retrieval.
    """
    __tablename__ = "kb_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False)

    # Chunk content
    chunk_index = Column(Integer, nullable=False)  # 0-based position within document
    content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=True)

    # Source location within document
    page_number = Column(Integer, nullable=True)
    start_char = Column(Integer, nullable=True)  # Character offset in original document
    end_char = Column(Integer, nullable=True)

    # Vector embedding (768 dimensions for nomic-embed-text-v2)
    # pgvector column — uses HNSW index for fast approximate nearest neighbor search
    embedding = Column(Vector(768)) if Vector else Column(JSON)

    # Extra context (section heading, etc.)
    chunk_metadata = Column("metadata", JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    document = relationship("KBDocument", back_populates="chunks")

    __table_args__ = (
        Index("idx_kb_chunk_doc", "document_id"),
        Index("idx_kb_chunk_order", "document_id", "chunk_index"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "token_count": self.token_count,
            "page_number": self.page_number,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "metadata": self.chunk_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
