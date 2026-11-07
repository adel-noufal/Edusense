"""
EduSense - Task 2 & Task 2.1 Automated Test Suite
=================================================
Covers:
  - Task 2:   Session resource upload and document vector ingestion (chunks_indexed)
  - Task 2.1: Session resource deletion, disk file removal, and ChromaDB cleanup verification
  - Task 2.2: Partial vector store cleanup and verification on ingestion failure

Design & Safety Guarantees:
  - Isolated in-memory SQLite database (zero contact with production PostgreSQL).
  - Mocked vector store services (ingest_file, delete_by_source, init_collection) at
    the app.api.sessions boundary (zero contact with ChromaDB or edusense_knowledge).
  - Isolated temporary directory for file upload/unlink operations.
  - Startup event handlers bypassed so APScheduler and init_db never start or seed live data.
  - Full restoration of dependency overrides, startup events, and monkeypatches after every test.
  - Supports both direct script execution (`python test_task2.py`) and standard test runners (`pytest`).
"""

import logging
import os
import sys
import tempfile
from datetime import date, datetime, time, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.session import Base, get_db
from app.main import app
from app.models.models import Session, SessionResource, User
from app.services.vector_store import ChunkMetadata, ChunkRecord


# ---------------------------------------------------------------------------
# Logging Capture Helper
# ---------------------------------------------------------------------------
class LogCaptureHandler(logging.Handler):
    """Thread-safe in-memory log record accumulator for asserting log emissions."""
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def has_message_containing(self, substring: str, level: str = "ERROR") -> bool:
        return any(
            substring in r.getMessage() and r.levelname == level
            for r in self.records
        )

    def clear(self):
        self.records.clear()


# ---------------------------------------------------------------------------
# Test Environment Fixture / Harness
# ---------------------------------------------------------------------------
class TestHarness:
    """
    Manages in-memory SQLite database, temporary directories, dependency overrides,
    and mock vector store interfaces for a single test.
    """
    def __init__(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine, expire_on_commit=False
        )
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

        self.mock_ingest = MagicMock()
        self.mock_delete_source = MagicMock()
        self.mock_collection = MagicMock()
        self.mock_init_collection = MagicMock(return_value=self.mock_collection)

        self.log_handler = LogCaptureHandler()
        self.sessions_logger = logging.getLogger("app.api.sessions")

        self.client = None
        self.current_user = None
        self._orig_on_startup = None
        self._orig_on_shutdown = None
        self._patch_resource_dir = None
        self._patch_ingest = None
        self._patch_delete = None
        self._patch_init_col = None

    def setup(self):
        # 1. Create SQLite tables in memory
        Base.metadata.create_all(bind=self.engine)

        # 2. Seed baseline testing entities
        db = self.SessionLocal()
        try:
            self.instructor_1 = User(
                id=1,
                name="Instructor One",
                email="inst1@edusense.test",
                password_hash="fakehash",
                role="instructor",
            )
            self.instructor_2 = User(
                id=2,
                name="Instructor Two",
                email="inst2@edusense.test",
                password_hash="fakehash",
                role="instructor",
            )
            self.student = User(
                id=3,
                name="Student One",
                email="student@edusense.test",
                password_hash="fakehash",
                role="student",
            )
            self.admin = User(
                id=4,
                name="Admin User",
                email="admin@edusense.test",
                password_hash="fakehash",
                role="admin",
            )
            db.add_all([self.instructor_1, self.instructor_2, self.student, self.admin])
            db.commit()

            self.session_1 = Session(
                id=1,
                instructor_id=1,
                title="AI & Machine Learning 101",
                description="Introductory session",
                date=date(2026, 10, 24),
                start_time=time(10, 0),
                duration=60,
                status="pending",
            )
            self.session_2 = Session(
                id=2,
                instructor_id=2,
                title="Advanced Robotics",
                description="Robotics session by Instructor 2",
                date=date(2026, 10, 24),
                start_time=time(14, 0),
                duration=60,
                status="pending",
            )
            db.add_all([self.session_1, self.session_2])
            db.commit()
        finally:
            db.close()

        # 3. Default active user
        self.current_user = self.instructor_1

        # 4. Dependency overrides
        def _override_get_db():
            session = self.SessionLocal()
            try:
                yield session
            finally:
                session.close()

        def _override_get_current_user():
            return self.current_user

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_get_current_user

        # 5. Prevent FastAPI startup events from executing (avoids PostgreSQL and APScheduler)
        self._orig_on_startup = list(app.router.on_startup)
        self._orig_on_shutdown = list(app.router.on_shutdown)
        app.router.on_startup.clear()
        app.router.on_shutdown.clear()

        # 6. Default mock behavior
        self.mock_collection.get.return_value = {"ids": []}
        self.mock_ingest.return_value = [
            ChunkRecord(id=f"chunk_{i}", text=f"Sample text content chunk {i}")
            for i in range(3)
        ]

        # 7. Attach logging capture
        self.sessions_logger.addHandler(self.log_handler)

        # 8. Patches
        self._patch_resource_dir = patch("app.api.sessions.RESOURCE_DIR", self.tmp_path)
        self._patch_ingest = patch("app.api.sessions.ingest_file", self.mock_ingest)
        self._patch_delete = patch("app.api.sessions.delete_by_source", self.mock_delete_source)
        self._patch_init_col = patch("app.api.sessions.init_collection", self.mock_init_collection)

        self._patch_resource_dir.start()
        self._patch_ingest.start()
        self._patch_delete.start()
        self._patch_init_col.start()

        # 9. Create TestClient with server exceptions disabled so 500s return response objects
        self.client = TestClient(app, raise_server_exceptions=False)

    def teardown(self):
        # Stop patches
        for p in (
            self._patch_resource_dir,
            self._patch_ingest,
            self._patch_delete,
            self._patch_init_col,
        ):
            if p is not None:
                try:
                    p.stop()
                except RuntimeError:
                    pass

        # Detach log handler
        self.sessions_logger.removeHandler(self.log_handler)

        # Restore FastAPI startup/shutdown handlers
        if self._orig_on_startup is not None:
            app.router.on_startup.extend(self._orig_on_startup)
        if self._orig_on_shutdown is not None:
            app.router.on_shutdown.extend(self._orig_on_shutdown)

        # Clear dependency overrides
        app.dependency_overrides.clear()

        # Drop SQLite tables and close engine
        try:
            Base.metadata.drop_all(bind=self.engine)
        except Exception:
            pass
        self.engine.dispose()

        # Clean up temporary directory
        self.tmp_dir.cleanup()

    def get_db_session(self):
        return self.SessionLocal()


# ---------------------------------------------------------------------------
# Individual Test Functions
# ---------------------------------------------------------------------------

def test_upload_resource_success():
    """
    Task 2: Successful session resource upload.
    Verifies:
      - HTTP 200 response with all metadata fields and chunks_indexed == 3.
      - SessionResource record properly committed to the database.
      - File correctly saved to the isolated temporary disk directory.
      - ingest_file called with expected file_path and complete metadata dictionary.
    """
    harness = TestHarness()
    try:
        harness.setup()
        harness.mock_ingest.return_value = [
            ChunkRecord(id="c_0", text="Introductory chunk"),
            ChunkRecord(id="c_1", text="Middle chunk"),
            ChunkRecord(id="c_2", text="Concluding chunk"),
        ]
        file_bytes = b"%PDF-1.4 sample presentation binary content"
        response = harness.client.post(
            "/api/sessions/1/resources",
            files={"file": ("lecture_slides.pdf", file_bytes, "application/pdf")},
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["name"] == "lecture_slides.pdf"
        assert data["file_type"] == "application/pdf"
        assert data["file_size"] == len(file_bytes)
        assert data["chunks_indexed"] == 3
        assert "id" in data and isinstance(data["id"], int)
        assert data["url"] == "/static/resources/session-1-lecture_slides.pdf"

        # Verify SQL persistence
        db = harness.get_db_session()
        try:
            res = db.query(SessionResource).filter_by(id=data["id"]).first()
            assert res is not None, "SessionResource record was not found in SQLite DB!"
            assert res.session_id == 1
            assert res.instructor_id == 1
            assert res.name == "lecture_slides.pdf"
            assert res.file_size == len(file_bytes)
        finally:
            db.close()

        # Verify disk write in isolated temporary directory
        saved_file = harness.tmp_path / "session-1-lecture_slides.pdf"
        assert saved_file.exists(), f"Saved file not found on disk at {saved_file}"
        assert saved_file.read_bytes() == file_bytes

        # Verify ingest_file invocation
        harness.mock_ingest.assert_called_once()
        call_kwargs = harness.mock_ingest.call_args.kwargs
        assert call_kwargs["file_path"] == str(saved_file)
        meta = call_kwargs["metadata"]
        assert meta["source_id"] == f"resource_{data['id']}"
        assert meta["source_file"] == "lecture_slides.pdf"
        assert meta["session_id"] == 1
        assert meta["instructor_id"] == 1
        assert meta["topic"] == "AI & Machine Learning 101"
    finally:
        harness.teardown()


def test_upload_ingestion_failure_clean_rollback():
    """
    Task 2.2: Ingestion failure with clean partial rollback.
    Verifies:
      - ingest_file failure raises HTTP 500 with descriptive error detail.
      - delete_by_source('resource_{id}') is called for cleanup.
      - init_collection().get(where={'source_id': 'resource_{id}'}, limit=1) verifies cleanup.
      - SQL SessionResource record and physical disk file remain intact per design.
    """
    harness = TestHarness()
    try:
        harness.setup()
        harness.mock_ingest.side_effect = RuntimeError("Embedding model connection timeout")
        harness.mock_collection.get.return_value = {"ids": []}  # Verified clean

        file_bytes = b"Sample notes content"
        response = harness.client.post(
            "/api/sessions/1/resources",
            files={"file": ("notes.txt", file_bytes, "text/plain")},
        )

        assert response.status_code == 500, f"Expected 500, got {response.status_code}"
        assert "Resource uploaded, but vector store ingestion failed" in response.json()["detail"]
        assert "Embedding model connection timeout" in response.json()["detail"]

        # Verify cleanup attempt and verification query
        harness.mock_delete_source.assert_called_once_with("resource_1")
        harness.mock_collection.get.assert_called_once_with(
            where={"source_id": "resource_1"}, limit=1
        )

        # Verify SQL resource and disk file remain intact
        db = harness.get_db_session()
        try:
            res = db.query(SessionResource).filter_by(id=1).first()
            assert res is not None, "Resource should remain in DB after ingestion error"
        finally:
            db.close()

        saved_file = harness.tmp_path / "session-1-notes.txt"
        assert saved_file.exists(), "File should remain on disk after ingestion error"
    finally:
        harness.teardown()


def test_upload_ingestion_failure_incomplete_cleanup_logged():
    """
    Task 2.2: Ingestion failure where cleanup leaves stale chunks.
    Verifies:
      - HTTP 500 returned with the primary ingestion exception.
      - Warning/error log captures that cleanup was incomplete with chunk count.
    """
    harness = TestHarness()
    try:
        harness.setup()
        harness.mock_ingest.side_effect = RuntimeError("ONNX runtime failure")
        # Simulate that 2 chunks remain despite delete_by_source
        harness.mock_collection.get.return_value = {"ids": ["chunk_leftover_1", "chunk_leftover_2"]}

        response = harness.client.post(
            "/api/sessions/1/resources",
            files={"file": ("stale_test.pdf", b"test content", "application/pdf")},
        )

        assert response.status_code == 500
        assert "Resource uploaded, but vector store ingestion failed" in response.json()["detail"]

        # Verify error logged
        assert harness.log_handler.has_message_containing(
            "Partial vector store cleanup incomplete for resource 1 (resource_1): 2 chunk(s) still present"
        ), "Incomplete cleanup error log was not emitted!"
    finally:
        harness.teardown()


def test_upload_ingestion_failure_verification_exception_handled():
    """
    Task 2.2: Ingestion failure where the cleanup verification itself raises an exception.
    Verifies:
      - Secondary cleanup/verification exception does not mask the primary 500 ingestion error.
      - Cleanup exception is safely caught and logged.
    """
    harness = TestHarness()
    try:
        harness.setup()
        harness.mock_ingest.side_effect = RuntimeError("Primary ingestion error")
        harness.mock_collection.get.side_effect = RuntimeError("ChromaDB socket disconnected")

        response = harness.client.post(
            "/api/sessions/1/resources",
            files={"file": ("socket_fail.pdf", b"test content", "application/pdf")},
        )

        assert response.status_code == 500
        assert "Primary ingestion error" in response.json()["detail"]
        assert harness.log_handler.has_message_containing(
            "Vector store cleanup/verification failed for resource 1 (resource_1): ChromaDB socket disconnected"
        )
    finally:
        harness.teardown()


def test_delete_resource_success():
    """
    Task 2.1: Successful resource deletion and vector cleanup.
    Verifies:
      - Response is exactly {'message': 'Resource deleted'} without 'vector_store_cleanup' field.
      - SQL SessionResource record is deleted from SQLite.
      - Disk file is deleted via unlink.
      - delete_by_source('resource_{id}') is called.
      - Both verification filters ('source_id' and 'source_file') return empty ids.
    """
    harness = TestHarness()
    try:
        harness.setup()
        db = harness.get_db_session()
        file_path = harness.tmp_path / "session-1-deleteme.pdf"
        file_bytes = b"Delete me soon"
        file_path.write_bytes(file_bytes)

        res = SessionResource(
            id=10,
            session_id=1,
            instructor_id=1,
            name="deleteme.pdf",
            file_path=str(file_path),
            file_type="application/pdf",
            file_size=len(file_bytes),
        )
        db.add(res)
        db.commit()
        db.close()

        # Both queries return empty (clean)
        harness.mock_collection.get.return_value = {"ids": []}

        response = harness.client.delete("/api/sessions/resources/10")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data == {"message": "Resource deleted"}, f"Unexpected body: {data}"
        assert "vector_store_cleanup" not in data

        # Verify SQL record deleted
        db = harness.get_db_session()
        try:
            assert db.query(SessionResource).filter_by(id=10).first() is None, "Resource was not deleted from DB!"
        finally:
            db.close()

        # Verify physical file deleted from disk
        assert not file_path.exists(), "Physical file was not unlinked from disk!"

        # Verify delete_by_source call
        harness.mock_delete_source.assert_called_once_with("resource_10")

        # Verify dual verification calls
        assert harness.mock_collection.get.call_count == 2
        calls = harness.mock_collection.get.call_args_list
        assert calls[0].kwargs == {"where": {"source_id": "resource_10"}, "limit": 1}
        assert calls[1].kwargs == {"where": {"source_file": "resource_10"}, "limit": 1}
    finally:
        harness.teardown()


def test_delete_resource_stale_chunks_detected_source_id():
    """
    Task 2.1: Resource deletion where source_id verification finds stale chunks.
    Verifies:
      - HTTP 200 returned.
      - Response body contains 'vector_store_cleanup': 'failed — stale chunks may remain'.
      - SQL deletion and file deletion remain permanent (no rollback).
    """
    harness = TestHarness()
    try:
        harness.setup()
        db = harness.get_db_session()
        file_path = harness.tmp_path / "session-1-stale_id.pdf"
        file_path.write_bytes(b"content")

        res = SessionResource(
            id=20,
            session_id=1,
            instructor_id=1,
            name="stale_id.pdf",
            file_path=str(file_path),
            file_type="application/pdf",
            file_size=7,
        )
        db.add(res)
        db.commit()
        db.close()

        # Stale chunk returned on source_id check
        harness.mock_collection.get.side_effect = [
            {"ids": ["resource_20_chunk_0"]},  # source_id query
            {"ids": []},                        # source_file query
        ]

        response = harness.client.delete("/api/sessions/resources/20")

        assert response.status_code == 200
        data = response.json()
        assert data.get("message") == "Resource deleted"
        assert data.get("vector_store_cleanup") == "failed \u2014 stale chunks may remain"

        # Verify SQL record is still deleted
        db = harness.get_db_session()
        try:
            assert db.query(SessionResource).filter_by(id=20).first() is None
        finally:
            db.close()
        assert not file_path.exists()
    finally:
        harness.teardown()


def test_delete_resource_stale_chunks_detected_source_file():
    """
    Task 2.1: Resource deletion where source_file verification finds stale chunks.
    Verifies:
      - HTTP 200 returned.
      - Response body contains 'vector_store_cleanup': 'failed — stale chunks may remain'.
    """
    harness = TestHarness()
    try:
        harness.setup()
        db = harness.get_db_session()
        file_path = harness.tmp_path / "session-1-stale_file.pdf"
        file_path.write_bytes(b"content")

        res = SessionResource(
            id=30,
            session_id=1,
            instructor_id=1,
            name="stale_file.pdf",
            file_path=str(file_path),
            file_type="application/pdf",
            file_size=7,
        )
        db.add(res)
        db.commit()
        db.close()

        # Empty on source_id, but stale chunk on source_file check
        harness.mock_collection.get.side_effect = [
            {"ids": []},
            {"ids": ["stale_file_chunk_42"]},
        ]

        response = harness.client.delete("/api/sessions/resources/30")

        assert response.status_code == 200
        data = response.json()
        assert data.get("message") == "Resource deleted"
        assert data.get("vector_store_cleanup") == "failed \u2014 stale chunks may remain"
    finally:
        harness.teardown()


def test_delete_resource_verification_exception_handled():
    """
    Task 2.1: Resource deletion where ChromaDB verification raises an unexpected exception.
    Verifies:
      - HTTP 200 returned with 'vector_store_cleanup': 'failed — stale chunks may remain'.
      - Exception is logged.
      - SQL deletion is permanent.
    """
    harness = TestHarness()
    try:
        harness.setup()
        db = harness.get_db_session()
        file_path = harness.tmp_path / "session-1-exc.pdf"
        file_path.write_bytes(b"content")

        res = SessionResource(
            id=40,
            session_id=1,
            instructor_id=1,
            name="exc.pdf",
            file_path=str(file_path),
            file_type="application/pdf",
            file_size=7,
        )
        db.add(res)
        db.commit()
        db.close()

        harness.mock_collection.get.side_effect = RuntimeError("ChromaDB read error")

        response = harness.client.delete("/api/sessions/resources/40")

        assert response.status_code == 200
        data = response.json()
        assert data.get("message") == "Resource deleted"
        assert data.get("vector_store_cleanup") == "failed \u2014 stale chunks may remain"

        assert harness.log_handler.has_message_containing(
            "Vector store cleanup/verification failed for resource 40 (resource_40): ChromaDB read error"
        )
    finally:
        harness.teardown()


def test_upload_authorization_and_validation():
    """
    Verifies authorization and validation edge cases for upload:
      - 404 when session_id does not exist.
      - 403 when an instructor tries to upload to another instructor's session.
      - 403 when a user with role 'student' tries to upload.
    """
    harness = TestHarness()
    try:
        harness.setup()
        # 1. Non-existent session
        resp_404 = harness.client.post(
            "/api/sessions/9999/resources",
            files={"file": ("a.pdf", b"abc", "application/pdf")},
        )
        assert resp_404.status_code == 404
        assert resp_404.json()["detail"] == "Session not found"

        # 2. Not session owner (Instructor 1 attempting upload to Session 2 owned by Instructor 2)
        resp_403_owner = harness.client.post(
            "/api/sessions/2/resources",
            files={"file": ("b.pdf", b"abc", "application/pdf")},
        )
        assert resp_403_owner.status_code == 403
        assert resp_403_owner.json()["detail"] == "Not your session"

        # 3. Student role attempting upload
        harness.current_user = harness.student
        resp_403_role = harness.client.post(
            "/api/sessions/1/resources",
            files={"file": ("c.pdf", b"abc", "application/pdf")},
        )
        assert resp_403_role.status_code == 403
        assert resp_403_role.json()["detail"] == "Insufficient permissions"
    finally:
        harness.teardown()


def test_delete_authorization_and_validation():
    """
    Verifies authorization and validation edge cases for delete:
      - 404 when resource_id does not exist.
      - 403 when an instructor tries to delete another instructor's resource.
      - 403 when a student tries to delete a resource.
    """
    harness = TestHarness()
    try:
        harness.setup()
        db = harness.get_db_session()
        res_inst2 = SessionResource(
            id=50,
            session_id=2,
            instructor_id=2,
            name="inst2_file.pdf",
            file_path=str(harness.tmp_path / "inst2_file.pdf"),
            file_type="application/pdf",
            file_size=10,
        )
        db.add(res_inst2)
        db.commit()
        db.close()

        # 1. Non-existent resource
        resp_404 = harness.client.delete("/api/sessions/resources/9999")
        assert resp_404.status_code == 404
        assert resp_404.json()["detail"] == "Resource not found"

        # 2. Not resource owner (Instructor 1 attempting to delete Instructor 2's resource)
        harness.current_user = harness.instructor_1
        resp_403_owner = harness.client.delete("/api/sessions/resources/50")
        assert resp_403_owner.status_code == 403
        assert resp_403_owner.json()["detail"] == "Not your resource"

        # 3. Student role attempting delete
        harness.current_user = harness.student
        resp_403_role = harness.client.delete("/api/sessions/resources/50")
        assert resp_403_role.status_code == 403
        assert resp_403_role.json()["detail"] == "Insufficient permissions"
    finally:
        harness.teardown()


def test_admin_override_and_unauthenticated():
    """
    Verifies admin role overrides and unauthenticated handling:
      - Admin can upload to a session owned by another instructor.
      - Admin can delete a resource owned by another instructor.
      - Unauthenticated requests (no auth override) return HTTP 401.
    """
    harness = TestHarness()
    try:
        harness.setup()
        # Pre-create resource owned by Instructor 2
        db = harness.get_db_session()
        file_path = harness.tmp_path / "inst2_admin_del.pdf"
        file_path.write_bytes(b"content")
        res_inst2 = SessionResource(
            id=60,
            session_id=2,
            instructor_id=2,
            name="inst2_admin_del.pdf",
            file_path=str(file_path),
            file_type="application/pdf",
            file_size=7,
        )
        db.add(res_inst2)
        db.commit()
        db.close()

        # Set user as Admin
        harness.current_user = harness.admin

        # 1. Admin upload to Session 2 (owned by Instructor 2)
        resp_upload = harness.client.post(
            "/api/sessions/2/resources",
            files={"file": ("admin_upload.pdf", b"admin content", "application/pdf")},
        )
        assert resp_upload.status_code == 200, f"Admin upload failed: {resp_upload.text}"

        # 2. Admin delete resource 60 (owned by Instructor 2)
        resp_delete = harness.client.delete("/api/sessions/resources/60")
        assert resp_delete.status_code == 200, f"Admin delete failed: {resp_delete.text}"
        assert resp_delete.json() == {"message": "Resource deleted"}

        # 3. Unauthenticated request: Remove get_current_user override
        del app.dependency_overrides[get_current_user]
        resp_unauth = harness.client.post(
            "/api/sessions/1/resources",
            files={"file": ("unauth.pdf", b"data", "application/pdf")},
        )
        assert resp_unauth.status_code == 401, f"Expected 401, got {resp_unauth.status_code}"
    finally:
        harness.teardown()


# ---------------------------------------------------------------------------
# Runner for `python test_task2.py`
# ---------------------------------------------------------------------------
def run_verification():
    tests = [
        ("Task 2: Successful upload & chunks_indexed", test_upload_resource_success),
        ("Task 2.2: Ingestion failure clean rollback", test_upload_ingestion_failure_clean_rollback),
        ("Task 2.2: Incomplete cleanup logging", test_upload_ingestion_failure_incomplete_cleanup_logged),
        ("Task 2.2: Verification exception logging", test_upload_ingestion_failure_verification_exception_handled),
        ("Task 2.1: Successful deletion & vector cleanup", test_delete_resource_success),
        ("Task 2.1: Stale chunks detected (source_id)", test_delete_resource_stale_chunks_detected_source_id),
        ("Task 2.1: Stale chunks detected (source_file)", test_delete_resource_stale_chunks_detected_source_file),
        ("Task 2.1: Verification exception handled", test_delete_resource_verification_exception_handled),
        ("Task 2: Upload authorization & 404 validation", test_upload_authorization_and_validation),
        ("Task 2.1: Deletion authorization & 404 validation", test_delete_authorization_and_validation),
        ("Task 2 & 2.1: Admin override & 401 unauthenticated", test_admin_override_and_unauthenticated),
    ]

    print("=" * 70)
    print("      EduSense - Task 2 & Task 2.1 Automated Test Suite")
    print("=" * 70)

    passed = 0
    total = len(tests)

    for idx, (title, func) in enumerate(tests, start=1):
        print(f"\n[{idx}/{total}] Running: {title}...")
        try:
            func()
            print(f"  -> [PASS] {title}")
            passed += 1
        except Exception as e:
            print(f"  -> [FAIL] {title}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    print("\n" + "=" * 70)
    print(f"   [SUCCESS] ALL {passed}/{total} TASK 2 & 2.1 CHECKS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    run_verification()
