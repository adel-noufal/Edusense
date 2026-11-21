import os
import sys
import pytest

BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

_TEST_DB = os.path.join(BACKEND_ROOT, "edusense_test.db").replace("\\", "/")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])


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
}


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_LIVE_PROVIDERS") == "1":
        return
    skip_live = pytest.mark.skip(reason="live provider test; set RUN_LIVE_PROVIDERS=1 to run")
    for item in items:
        if item.path.name in LIVE_TEST_FILES:
            item.add_marker(skip_live)
