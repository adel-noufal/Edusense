import sqlite3
from sqlalchemy import create_engine, text

# Connect to both databases
sqlite_conn = sqlite3.connect('edusense.db')
sqlite_conn.row_factory = sqlite3.Row
pg_engine = create_engine('postgresql+psycopg2://edusense:edusense@localhost:5432/edusense')

tables = [
    'users', 'profiles', 'sessions', 'feedback',
    'video_projects', 'session_registrations',
    'emotion_logs', 'reports', 'quizzes', 'session_notes'
]

cursor = sqlite_conn.cursor()

for table in tables:
    print(f'Migrating {table}...')
    cursor.execute(f'SELECT * FROM {table}')
    rows = cursor.fetchall()
    
    if not rows:
        print(f'  No data in {table}, skipping.')
        continue

    with pg_engine.begin() as pg_conn:
        for row in rows:
            row_dict = dict(row)
            cols = ', '.join(row_dict.keys())
            placeholders = ', '.join([f':{k}' for k in row_dict.keys()])
            sql = text(f'INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT DO NOTHING')
            try:
                pg_conn.execute(sql, row_dict)
            except Exception as e:
                print(f'  Skipped a row in {table}: {e}')

    print(f'  Done! {len(rows)} rows migrated.')

print('\nMigration complete!')
sqlite_conn.close()