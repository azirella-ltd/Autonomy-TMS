#!/usr/bin/env python3
"""
Batch RAG ingestion — directly populates autonomy_kb on Acer-Nitro.

Three input sources (all run together each time):
  1. docs/           — platform knowledge base (PDFs + Markdown)
  2. data/rag_intake/ — customer drop folder (any file → category subdir)
  3. data/rag_sources.yaml — URL sources (Google Drive, SharePoint, direct URLs)

Already-indexed files are skipped. Failed/empty records are retried.

Usage:
    python3 scripts/ingest_rag.py [--dry-run] [--sources-only] [--intake-only]
"""

import argparse
import io
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin

import fitz  # PyMuPDF
import httpx
import psycopg2
import yaml
from psycopg2.extras import execute_values

# ── Config ────────────────────────────────────────────────────────────────────
DB_DSN        = "postgresql://kb_user:kb_password@localhost:5432/autonomy_kb"
EMBED_URL     = "http://localhost:11434/v1/embeddings"
EMBED_MODEL   = "nomic-embed-text"
EMBED_DIMS    = 768
CHUNK_SIZE    = 1024   # chars
CHUNK_OVERLAP = 200
TENANT_ID     = 1
BATCH_SIZE    = 8      # chunks per embedding call
REPO_ROOT     = Path(__file__).parent.parent
DOCS_ROOT     = REPO_ROOT / "docs"
INTAKE_ROOT   = REPO_ROOT / "data" / "rag_intake"
SOURCES_FILE  = REPO_ROOT / "data" / "rag_sources.yaml"

# ── Category mapping (path pattern → category) ────────────────────────────────
CATEGORY_MAP = [
    (r"knowledge/downloads/Oliver_Wight",      "sop_ibp"),
    (r"knowledge/downloads/.*MEIO|knowledge/downloads/CMU|knowledge/downloads/Polimi|knowledge/downloads/arXiv", "inventory_optimization"),
    (r"knowledge/downloads/AATP",              "atp_ctp"),
    (r"knowledge/01_MPS|knowledge/02_Systems|knowledge/03_ERP|knowledge/04_Kinaxis_Master", "mps_mrp"),
    (r"knowledge/06_Kinaxis_Capacity",         "capacity_planning"),
    (r"knowledge/08_Kinaxis_Inventory",        "inventory_optimization"),
    (r"knowledge/10_OMP|knowledge/11_OMP",     "planning_strategy"),
    (r"knowledge/14_Stanford|knowledge/21_Stochastic|knowledge/Conformal|knowledge/Risk-based|knowledge/Simio", "stochastic_planning"),
    (r"knowledge/16_Safety|knowledge/17_MIT.*Safety|knowledge/18_MIT.*Inventory|knowledge/19_Vandeput|knowledge/20_Inventory|knowledge/MEIO", "inventory_optimization"),
    (r"knowledge/Powell",                      "decision_framework"),
    (r"knowledge/GNN|knowledge/Graph_Neural|knowledge/Learning.*Production|knowledge/Less.*TRM|knowledge/Simio_AI|knowledge/BCG", "ai_ml"),
    (r"knowledge/LeCun",                       "ai_planning"),
    (r"knowledge/Strategic.*Agentic|knowledge/AUTONOMY.*STRATEGY|knowledge/DAYBREAK", "strategy"),
    (r"knowledge/Stop.*Guessing|knowledge/Distributor.*Powell", "decision_framework"),
    (r"knowledge/AWS_SC|knowledge/ATP_CTP|knowledge/Capacity_Planning|knowledge/Demand_Planning|knowledge/DDMRP|knowledge/Decision_Intelligence|knowledge/DRP|knowledge/MEIO_Inventory|knowledge/Order_Execution|knowledge/MRP_Logic|knowledge/Lokad|knowledge/Powell_Planning|knowledge/SCP_KNOWLEDGE|knowledge/SOP_IBP|knowledge/SCOR|knowledge/Supply_Network|knowledge/Supply_Chain_Metrics|knowledge/Conformal_Prediction", "supply_chain_knowledge"),
    (r"The_Beer_Game",                         "beer_game"),
    (r"external",                              "strategy"),
    (r"internal/POWELL|internal/TRM|internal/AGENT|internal/HIVE|internal/AGENTIC", "ai_planning"),
    (r"internal",                              "internal_docs"),
]

def get_category(path: str) -> str:
    for pattern, cat in CATEGORY_MAP:
        if re.search(pattern, path, re.IGNORECASE):
            return cat
    return "general"

# ── Text extraction ────────────────────────────────────────────────────────────
def extract_pdf(path: Path) -> list[tuple[str, int]]:
    """Returns list of (text, page_number) tuples. Falls back to OCR for image-based pages."""
    doc = fitz.open(str(path))
    pages = []
    text_found = False
    for i, page in enumerate(doc, start=1):
        text = page.get_text().strip().replace("\x00", "")  # strip NUL bytes
        if text:
            pages.append((text, i))
            text_found = True

    # If no text at all, try OCR via page.get_text("dict") with tesseract
    if not text_found:
        try:
            import pytesseract
            from PIL import Image
            import io
            doc2 = fitz.open(str(path))
            for i, page in enumerate(doc2, start=1):
                mat = fitz.Matrix(2, 2)  # 2x zoom for better OCR accuracy
                pix = page.get_pixmap(matrix=mat)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img).strip()
                if text:
                    pages.append((text, i))
            doc2.close()
        except Exception:
            pass  # OCR not available — leave empty

    doc.close()
    return pages

def extract_md(path: Path) -> list[tuple[str, int]]:
    text = path.read_text(errors="replace").strip()
    return [(text, None)] if text else []

# ── Chunking ───────────────────────────────────────────────────────────────────
def chunk_text(text: str, page: int | None) -> list[dict]:
    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end].strip()
        if chunk:
            chunks.append({"content": chunk, "page": page,
                           "start": start, "end": min(end, len(text)), "idx": idx})
            idx += 1
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks

# ── Embedding ──────────────────────────────────────────────────────────────────
def embed_batch(texts: list[str]) -> list[list[float]]:
    resp = httpx.post(
        EMBED_URL,
        json={"model": EMBED_MODEL, "input": texts},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    data.sort(key=lambda x: x["index"])
    return [d["embedding"] for d in data]

# ── DB helpers ─────────────────────────────────────────────────────────────────
def ensure_tables(conn):
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS kb_documents (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                uploaded_by INTEGER,
                title VARCHAR(500) NOT NULL,
                filename VARCHAR(500) NOT NULL,
                file_type VARCHAR(20) NOT NULL,
                file_size INTEGER,
                page_count INTEGER,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                error_message TEXT,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                embedding_model VARCHAR(200),
                embedding_dimensions INTEGER,
                category VARCHAR(100),
                description TEXT,
                tags JSON,
                created_at TIMESTAMP DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS kb_chunks (
                id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES kb_documents(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                token_count INTEGER,
                page_number INTEGER,
                start_char INTEGER,
                end_char INTEGER,
                embedding vector(768),
                metadata JSON,
                created_at TIMESTAMP DEFAULT now()
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_kb_doc_tenant ON kb_documents(tenant_id);
            """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_kb_chunk_doc ON kb_chunks(document_id);
            """)
        conn.commit()

def already_indexed(conn, filename: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM kb_documents WHERE filename = %s AND status = 'indexed'",
            (filename,)
        )
        return cur.fetchone() is not None

def delete_failed(conn, filename: str):
    """Remove failed/empty document records so they can be retried."""
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM kb_documents WHERE filename = %s AND status IN ('failed', 'pending')",
            (filename,)
        )
        conn.commit()

def insert_document(conn, path: Path, category: str, page_count: int | None) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO kb_documents
              (tenant_id, title, filename, file_type, file_size, page_count,
               status, embedding_model, embedding_dimensions, category)
            VALUES (%s,%s,%s,%s,%s,%s,'processing',%s,%s,%s)
            RETURNING id
        """, (
            TENANT_ID,
            path.stem.replace("_", " ").replace("-", " "),
            path.name,
            path.suffix.lstrip("."),
            path.stat().st_size,
            page_count,
            EMBED_MODEL,
            EMBED_DIMS,
            category,
        ))
        doc_id = cur.fetchone()[0]
        conn.commit()
    return doc_id

def insert_chunks(conn, doc_id: int, chunks: list[dict], embeddings: list[list[float]]):
    rows = [
        (
            doc_id,
            c["idx"],
            c["content"],
            len(c["content"].split()),
            c["page"],
            c["start"],
            c["end"],
            json.dumps(emb),   # store as JSON string then cast
        )
        for c, emb in zip(chunks, embeddings)
    ]
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO kb_chunks
              (document_id, chunk_index, content, token_count,
               page_number, start_char, end_char, embedding)
            VALUES %s
        """, rows, template="(%s,%s,%s,%s,%s,%s,%s,%s::vector)")
        conn.commit()

def mark_indexed(conn, doc_id: int, chunk_count: int):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE kb_documents
            SET status='indexed', chunk_count=%s, updated_at=now()
            WHERE id=%s
        """, (chunk_count, doc_id))
        conn.commit()

def mark_failed(conn, doc_id: int, error: str):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE kb_documents
            SET status='failed', error_message=%s, updated_at=now()
            WHERE id=%s
        """, (error[:500], doc_id))
        conn.commit()

# ── File discovery ─────────────────────────────────────────────────────────────
def collect_files() -> list[tuple[Path, str]]:
    """Returns list of (path, category) from docs/ and data/rag_intake/."""
    files = []

    # 1. docs/ — platform knowledge (PDFs + key Markdown)
    for pdf in sorted(DOCS_ROOT.rglob("*.pdf")):
        if any(p in str(pdf) for p in ["/progress/", "/debug_logs/"]):
            continue
        rel = str(pdf.relative_to(DOCS_ROOT))
        files.append((pdf, get_category(rel)))

    for md in sorted(DOCS_ROOT.rglob("*.md")):
        parts = str(md)
        if "/progress/" in parts or "/debug_logs/" in parts:
            continue
        if "/knowledge/" in parts:
            rel = str(md.relative_to(DOCS_ROOT))
            files.append((md, get_category(rel)))
        elif "/internal/" in parts and md.stat().st_size > 5000:
            rel = str(md.relative_to(DOCS_ROOT))
            files.append((md, get_category(rel)))

    # 2. data/rag_intake/{category}/ — customer drop folder
    if INTAKE_ROOT.exists():
        for cat_dir in sorted(INTAKE_ROOT.iterdir()):
            if not cat_dir.is_dir():
                continue
            category = cat_dir.name
            for f in sorted(cat_dir.iterdir()):
                if f.suffix.lower() in (".pdf", ".md", ".txt", ".docx", ".csv"):
                    files.append((f, category))

    return files


# ── URL source fetching ────────────────────────────────────────────────────────
def load_sources() -> list[dict]:
    if not SOURCES_FILE.exists():
        return []
    with open(SOURCES_FILE) as f:
        data = yaml.safe_load(f) or {}
    return data.get("sources", [])


def fetch_url_source(source: dict) -> tuple[bytes, str, str]:
    """Fetch a URL source. Returns (file_bytes, filename, file_type)."""
    url = source["url"]
    print(f"  Fetching {url} ... ", end="", flush=True)
    resp = httpx.get(url, follow_redirects=True, timeout=60,
                     headers={"User-Agent": "Autonomy-RAG/1.0"})
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    # Determine file type
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        file_type = "pdf"
        filename = urlparse(url).path.split("/")[-1] or "document.pdf"
        if not filename.endswith(".pdf"):
            filename += ".pdf"
    else:
        # Treat as HTML/text — extract visible text
        file_type = "html"
        filename = urlparse(url).path.strip("/").replace("/", "_") or "page"
        filename = re.sub(r"[^\w.-]", "_", filename)[:80] + ".html"

    return resp.content, filename, file_type


def extract_html(content: bytes) -> list[tuple[str, None]]:
    """Extract readable text from HTML using basic tag stripping."""
    text = content.decode("utf-8", errors="replace")
    # Remove scripts, styles, nav
    text = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", text,
                  flags=re.DOTALL | re.IGNORECASE)
    # Strip tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Decode HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">") \
               .replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    return [(text, None)] if len(text) > 100 else []


def fetch_gdrive_source(source: dict) -> list[tuple[bytes, str, str]]:
    """Fetch files from a public Google Drive folder."""
    folder_id = source["folder_id"]
    # Use Drive API v3 — works for public folders with API key or public share
    # Falls back to simple file listing via share URL
    api_key = source.get("api_key") or os.getenv("GDRIVE_API_KEY", "")
    results = []

    if api_key:
        url = (f"https://www.googleapis.com/drive/v3/files"
               f"?q='{folder_id}'+in+parents&key={api_key}&fields=files(id,name,mimeType)")
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        for item in resp.json().get("files", []):
            if "pdf" in item["mimeType"]:
                dl = (f"https://www.googleapis.com/drive/v3/files/{item['id']}"
                      f"?alt=media&key={api_key}")
                r = httpx.get(dl, timeout=60)
                r.raise_for_status()
                results.append((r.content, item["name"], "pdf"))
    else:
        print("  [gdrive] No API key — set GDRIVE_API_KEY env var for private folders")
    return results


def fetch_sharepoint_source(source: dict) -> list[tuple[bytes, str, str]]:
    """Fetch files from SharePoint via Microsoft Graph API."""
    tenant_id     = source.get("tenant_id")     or os.getenv("SHAREPOINT_TENANT_ID")
    client_id     = source.get("client_id")     or os.getenv("SHAREPOINT_CLIENT_ID")
    client_secret = source.get("client_secret") or os.getenv("SHAREPOINT_CLIENT_SECRET")

    if not all([tenant_id, client_id, client_secret]):
        print("  [sharepoint] Missing credentials — set SHAREPOINT_TENANT_ID/CLIENT_ID/CLIENT_SECRET")
        return []

    # Get access token
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_resp = httpx.post(token_url, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }, timeout=30)
    token_resp.raise_for_status()
    token = token_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # List files in SharePoint library
    site_url  = source["site_url"].rstrip("/")
    library   = source.get("library", "Documents")
    # Get site ID
    hostname  = urlparse(site_url).netloc
    site_path = urlparse(site_url).path
    site_resp = httpx.get(
        f"https://graph.microsoft.com/v1.0/sites/{hostname}:{site_path}",
        headers=headers, timeout=30
    )
    site_resp.raise_for_status()
    site_id = site_resp.json()["id"]

    # List drive items
    items_resp = httpx.get(
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{library}:/children",
        headers=headers, timeout=30
    )
    items_resp.raise_for_status()

    results = []
    for item in items_resp.json().get("value", []):
        name = item.get("name", "")
        if name.lower().endswith(".pdf"):
            dl_url = item.get("@microsoft.graph.downloadUrl")
            if dl_url:
                r = httpx.get(dl_url, timeout=60)
                r.raise_for_status()
                results.append((r.content, name, "pdf"))
    return results


def ingest_source(conn, source: dict, idx: int, total: int) -> tuple[int, int, int]:
    """Fetch and ingest a single URL source. Returns (ok, skipped, failed)."""
    ok = skipped = failed = 0
    src_type = source.get("type", "url")
    category = source.get("category", "general")

    print(f"\n[src {idx}/{total}] type={src_type} category={category}")

    try:
        if src_type == "url":
            file_bytes, filename, file_type = fetch_url_source(source)
            items = [(file_bytes, filename, file_type)]
        elif src_type == "gdrive":
            items = [(b, n, t) for b, n, t in fetch_gdrive_source(source)]
        elif src_type == "sharepoint":
            items = [(b, n, t) for b, n, t in fetch_sharepoint_source(source)]
        else:
            print(f"  Unknown source type: {src_type}")
            return 0, 0, 1

        for file_bytes, filename, file_type in items:
            title = source.get("title") or filename
            tags  = source.get("tags")

            if already_indexed(conn, filename) and not source.get("force_refresh"):
                print(f"  SKIP {filename}")
                skipped += 1
                continue
            delete_failed(conn, filename)

            # Extract text
            if file_type == "pdf":
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = Path(tmp.name)
                pages = extract_pdf(tmp_path)
                tmp_path.unlink(missing_ok=True)
            elif file_type == "html":
                pages = extract_html(file_bytes)
            else:
                text = file_bytes.decode("utf-8", errors="replace").strip()
                pages = [(text, None)] if text else []

            if not pages:
                print(f"  EMPTY {filename}")
                skipped += 1
                continue

            all_chunks = []
            for text, page in pages:
                all_chunks.extend(chunk_text(text, page))

            if not all_chunks:
                skipped += 1
                continue

            # Insert
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO kb_documents
                      (tenant_id, title, filename, file_type, file_size,
                       status, embedding_model, embedding_dimensions, category, tags)
                    VALUES (%s,%s,%s,%s,%s,'processing',%s,%s,%s,%s)
                    RETURNING id
                """, (TENANT_ID, title, filename, file_type, len(file_bytes),
                      EMBED_MODEL, EMBED_DIMS, category, json.dumps(tags) if tags else None))
                doc_id = cur.fetchone()[0]
                conn.commit()

            all_embeddings = []
            for b in range(0, len(all_chunks), BATCH_SIZE):
                batch = all_chunks[b:b + BATCH_SIZE]
                all_embeddings.extend(embed_batch([c["content"] for c in batch]))
                time.sleep(0.05)

            insert_chunks(conn, doc_id, all_chunks, all_embeddings)
            mark_indexed(conn, doc_id, len(all_chunks))
            print(f"  OK {filename} — {len(all_chunks)} chunks")
            ok += 1

    except Exception as e:
        print(f"  FAILED: {e}")
        failed += 1

    return ok, skipped, failed


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",      action="store_true", help="List without ingesting")
    parser.add_argument("--sources-only", action="store_true", help="Only process URL sources")
    parser.add_argument("--intake-only",  action="store_true", help="Only process intake folder")
    args = parser.parse_args()

    run_docs    = not args.sources_only and not args.intake_only
    run_intake  = not args.sources_only
    run_sources = not args.intake_only

    files = collect_files() if (run_docs or run_intake) else []
    sources = load_sources() if run_sources else []

    print(f"Files: {len(files)}  |  URL sources: {len(sources)}")

    if args.dry_run:
        print("\n── Files ──")
        for path, cat in files:
            try:
                base = DOCS_ROOT if DOCS_ROOT in path.parents else INTAKE_ROOT
                rel = str(path.relative_to(base))
                prefix = "docs" if base == DOCS_ROOT else "intake"
            except ValueError:
                rel = path.name
                prefix = "?"
            print(f"  [{prefix}] [{cat:25s}] {rel}")
        print("\n── URL Sources ──")
        for s in sources:
            print(f"  [{s['type']:12s}] [{s.get('category','general'):20s}] {s.get('url') or s.get('folder_id') or s.get('site_url')}")
        return

    conn = psycopg2.connect(DB_DSN)
    ensure_tables(conn)

    ok = skipped = failed = 0

    for i, (path, category) in enumerate(files, 1):

        if already_indexed(conn, path.name):
            print(f"[{i:3d}/{len(files)}] SKIP  {path.name}")
            skipped += 1
            continue
        # Clean up any prior failed attempt before retrying
        delete_failed(conn, path.name)

        print(f"[{i:3d}/{len(files)}] {category:25s} {path.name} ... ", end="", flush=True)

        try:
            # Extract
            if path.suffix.lower() == ".pdf":
                pages = extract_pdf(path)
            else:
                pages = extract_md(path)

            if not pages:
                print("EMPTY")
                skipped += 1
                continue

            # Chunk
            all_chunks = []
            for text, page in pages:
                all_chunks.extend(chunk_text(text, page))

            if not all_chunks:
                print("NO CHUNKS")
                skipped += 1
                continue

            # Insert document record
            page_count = pages[-1][1] if path.suffix.lower() == ".pdf" else None
            doc_id = insert_document(conn, path, category, page_count)

            # Embed in batches
            all_embeddings = []
            for b in range(0, len(all_chunks), BATCH_SIZE):
                batch = all_chunks[b:b + BATCH_SIZE]
                texts = [c["content"] for c in batch]
                embs = embed_batch(texts)
                all_embeddings.extend(embs)
                time.sleep(0.05)

            # Insert chunks
            insert_chunks(conn, doc_id, all_chunks, all_embeddings)
            mark_indexed(conn, doc_id, len(all_chunks))

            print(f"{len(all_chunks)} chunks ✓")
            ok += 1

        except Exception as e:
            print(f"FAILED: {e}")
            try:
                if "doc_id" in dir():
                    mark_failed(conn, doc_id, str(e))
            except Exception:
                pass
            failed += 1

    # Process URL sources
    if sources:
        print(f"\n── URL Sources ({len(sources)}) ──")
        for i, source in enumerate(sources, 1):
            s_ok, s_skip, s_fail = ingest_source(conn, source, i, len(sources))
            ok += s_ok; skipped += s_skip; failed += s_fail

    conn.close()
    print(f"\nDone: {ok} indexed, {skipped} skipped, {failed} failed")

if __name__ == "__main__":
    main()
