# EduSense Task 1 & Task 2 Manifest

## Overview
This package contains only the files added or modified during:
- **Task 1: Vector Store Setup** (ChromaDB persistent client, local sentence-transformer embedding fallback, and test suite)
- **Task 2: Data Ingestion & Resource Management** (document chunking, ingestion pipeline, session resource upload/deletion vector synchronization, and comprehensive test suite)

## Files Manifest

| # | Relative Path | Task | Action | Description |
|---|---------------|------|--------|-------------|
| 1 | `backend/app/core/config.py` | Task 1 | **Modified** | Added `chroma_persist_dir` and `embedding_model` settings to `Settings` class. |
| 2 | `backend/app/services/vector_store.py` | Task 1 | **Added** | Core vector store implementation: ChromaDB persistent client, ONNX fallback embedding function, chunk management, semantic query, and source cleanup. |
| 3 | `backend/test_task1.py` | Task 1 | **Added** | Standalone verification script verifying vector store initialization, chunk ingestion, semantic similarity search, metadata filtering, deletion by source, and disk persistence. |
| 4 | `backend/app/services/ingestion.py` | Task 2 | **Added** | Document ingestion service: `chunk_text`, `_build_chunk_metadata`, and `ingest_file` for indexing uploaded documents into ChromaDB. |
| 5 | `backend/app/api/sessions.py` | Task 2 | **Modified** | Updated resource upload endpoint to ingest documents into vector store (with rollback on failure) and resource deletion endpoint to purge vector store chunks with verification. |
| 6 | `backend/test_task2.py` | Task 2 | **Added** | Automated test suite verifying resource upload, vector ingestion (`chunks_indexed`), resource deletion, ChromaDB cleanup, and failure rollback behavior. |
| 7 | `backend/.env.example` | Task 1 | **Modified** | Added configuration documentation for `EDUSENSE_CHROMA_PERSIST_DIR` and `EDUSENSE_EMBEDDING_MODEL`. |
| 8 | `backend/requirements.txt` | Tasks 1 & 2 | **Modified** | Added dependencies: `chromadb`, `sentence-transformers`, `pypdf`, and `python-pptx`. |
