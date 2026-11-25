import os
import sys
import pytest

BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

_TEST_DB = os.path.join(BACKEND_ROOT, "edusense_test.db").replace("\\", "/")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])

# P5: tests never touch the developer's live Knowledge Base. Uploads made by a
# test go to their own collection in their own Chroma directory (U7), so
# test_async_guide.pdf / notes.txt cannot appear in the real library again.
_TEST_CHROMA = os.path.join(BACKEND_ROOT, "data", "chroma_test")
os.environ.setdefault("CHROMA_PERSIST_DIR", _TEST_CHROMA)
os.environ.setdefault("EDUSENSE_CHROMA_PERSIST_DIR", _TEST_CHROMA)
os.environ.setdefault("EDUSENSE_RAG_COLLECTION", "edusense_knowledge_test")


@pytest.fixture(scope="session", autouse=True)
def seed_test_database():
    from app.db.seed import init_db
    from app.db.session import SessionLocal
    from app.models.models import User
    from app.core.security import hash_password
    init_db(seed=True)
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(email="instructor@edusense.local").first():
            db.add(User(name="Dr. Adel Hassan", email="instructor@edusense.local",
                        password_hash=hash_password("Password123"), role="instructor"))
        if not db.query(User).filter_by(email="student@edusense.local").first():
            db.add(User(name="Student", email="student@edusense.local",
                        password_hash=hash_password("Password123"), role="student"))
        db.commit()
    finally:
        db.close()

LIVE_TEST_FILES = {
    "test_part_a_multi_provider.py",
    "test_section7_web_search.py",
    "test_section6_key_rotation.py",
    "test_b9_prompt_enhancer.py",
}

# Needs the Vite dev server (and a browser) to exist. verify.bat runs the
# Playwright walkthrough instead, so these stay out of the default gate.
LIVE_SERVER_FILES = {
    "test_live_layout_emotion.py",
}


def pytest_collection_modifyitems(config, items):
    """Skip tests that need a live model or a running dev server by default.

    Every other test must pass with no network and no server, so a red gate
    always means a real regression. Set RUN_LIVE_PROVIDERS=1 / RUN_LIVE_SERVERS=1
    to run them deliberately.
    """
    skip_provider = pytest.mark.skip(reason="needs a live AI provider; set RUN_LIVE_PROVIDERS=1 to run")
    skip_server = pytest.mark.skip(reason="needs the Vite dev server; set RUN_LIVE_SERVERS=1 to run")
    for item in items:
        if os.getenv("RUN_LIVE_PROVIDERS") != "1" and (
            item.path.name in LIVE_TEST_FILES or item.get_closest_marker("live_provider")
        ):
            item.add_marker(skip_provider)
        if os.getenv("RUN_LIVE_SERVERS") != "1" and (
            item.path.name in LIVE_SERVER_FILES or item.get_closest_marker("live_server")
        ):
            item.add_marker(skip_server)
