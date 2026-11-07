from app.core.config import get_settings
from app.db.session import engine
from sqlalchemy import text

settings = get_settings()

def ensure_columns():
    url = settings.database_url
    if url.startswith('sqlite'):
        print('SQLite detected; please run a manual migration for SQLite to add columns.')
        return

    # Postgres: safe ALTER TABLE IF NOT EXISTS
    stmts = [
        "ALTER TABLE session_registrations ADD COLUMN IF NOT EXISTS attended BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS reminders_sent VARCHAR(200) NULL;",
    ]

    with engine.begin() as conn:
        for s in stmts:
            print('Executing:', s)
            conn.execute(text(s))
    print('Schema ensure complete.')

if __name__ == '__main__':
    ensure_columns()
