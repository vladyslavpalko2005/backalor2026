from __future__ import annotations
import sqlite3
import re
from contextlib import contextmanager

SCHEMA = '''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, google_sub TEXT NOT NULL UNIQUE, email TEXT NOT NULL,
 name TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS login_flows (
 state_hash TEXT PRIMARY KEY, poll_hash TEXT NOT NULL, nonce TEXT NOT NULL,
 verifier TEXT NOT NULL, status TEXT NOT NULL, user_id TEXT REFERENCES users(id), expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 0,
 snapshot TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS project_owner ON projects(owner_id);
CREATE TABLE IF NOT EXISTS project_shares (
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id),
 role TEXT NOT NULL CHECK(role IN ('reader','editor')),
 PRIMARY KEY(project_id,user_id)
);
CREATE INDEX IF NOT EXISTS share_user ON project_shares(user_id);

'''


# Preserve bound parameters while keeping the existing SQLite query vocabulary.
_PARAMETER = re.compile(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")|(?<!:):([A-Za-z_]\w*)|([?])")


def postgres_query(query):
    def substitute(match):
        if match[1]: return match[1]
        return '%('+match[2]+')s' if match[2] else '%s'
    return _PARAMETER.sub(substitute,query)


class Row(dict):
    def __getitem__(self,key):
        return list(self.values())[key] if isinstance(key,int) else super().__getitem__(key)


class PostgresCursor:
    def __init__(self,cursor): self.cursor=cursor
    def fetchone(self):
        row=self.cursor.fetchone()
        return Row(row) if row is not None else None
    def fetchall(self): return [Row(row) for row in self.cursor.fetchall()]
    def __iter__(self): return (Row(row) for row in self.cursor)


class PostgresConnection:
    def __init__(self,connection): self.connection=connection
    def execute(self,query,params=None):
        if query.strip().upper()=='BEGIN IMMEDIATE':
            # Match SQLite's short serialized write sections across API processes.
            # ZIP transfer and Google requests happen outside these sections.
            return PostgresCursor(self.connection.execute('SELECT pg_advisory_xact_lock(644204027)'))
        return PostgresCursor(self.connection.execute(postgres_query(query),params))


class Database:
    def __init__(self,path=None,url=''):
        self.url=url;self.path=path
        if url:
            if not url.startswith(('postgresql://','postgres://')):
                raise ValueError('BACKALOR_DATABASE_URL must be a PostgreSQL URL')
            self._initialize_postgres()
        else:
            if path is None: raise ValueError('A local database path is required')
            path.parent.mkdir(parents=True,exist_ok=True)
            with self.connect() as db:
                db.executescript(SCHEMA)
                columns={row['name'] for row in db.execute('PRAGMA table_info(projects)')}
                for column,definition in [('visibility',"TEXT NOT NULL DEFAULT 'private'"),('title_search',"TEXT NOT NULL DEFAULT ''"),('description_search',"TEXT NOT NULL DEFAULT ''")]:
                    if column not in columns: db.execute(f'ALTER TABLE projects ADD COLUMN {column} {definition}')
                db.execute('CREATE TABLE IF NOT EXISTS project_snapshots (name TEXT PRIMARY KEY, data BLOB NOT NULL)')
                self._indexes_and_search(db)

    def _initialize_postgres(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for statement in SCHEMA.replace('PRAGMA journal_mode=WAL;','').split(';'):
                if statement.strip(): db.execute(statement)
            for column,definition in [('visibility',"TEXT NOT NULL DEFAULT 'private'"),('title_search',"TEXT NOT NULL DEFAULT ''"),('description_search',"TEXT NOT NULL DEFAULT ''")]:
                db.execute(f'ALTER TABLE projects ADD COLUMN IF NOT EXISTS {column} {definition}')
            db.execute('CREATE TABLE IF NOT EXISTS project_snapshots (name TEXT PRIMARY KEY, data BYTEA NOT NULL)')
            # Supabase exposes public-schema tables through its Data API. No browser
            # role may read them; only this API's privileged server connection does.
            for table in ('users','sessions','login_flows','projects','project_shares','project_snapshots'):
                db.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
            self._indexes_and_search(db)

    def _indexes_and_search(self,db):
        db.execute('CREATE INDEX IF NOT EXISTS project_visibility ON projects(visibility)')
        db.execute('CREATE INDEX IF NOT EXISTS project_updated ON projects(updated_at DESC,id)')
        db.execute('CREATE INDEX IF NOT EXISTS project_owner_updated ON projects(owner_id,updated_at DESC,id)')
        db.execute('CREATE INDEX IF NOT EXISTS session_expiry ON sessions(expires_at)')
        db.execute('CREATE INDEX IF NOT EXISTS flow_expiry ON login_flows(expires_at)')
        # Only old rows need backfilling; Unicode normalization is computed once per edit.
        for row in db.execute("SELECT id,title,description FROM projects WHERE title_search='' ").fetchall():
            db.execute('UPDATE projects SET title_search=?,description_search=? WHERE id=?',
                       (row['title'].casefold(),row['description'].casefold(),row['id']))

    @contextmanager
    def connect(self):
        if self.url:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError:
                raise RuntimeError('Install requirements-backend.txt to use PostgreSQL') from None
            # Do not propagate a driver error that might contain connection credentials.
            try: connection=psycopg.connect(self.url,connect_timeout=10,row_factory=dict_row,autocommit=True)
            except psycopg.Error:
                raise RuntimeError('Cannot connect to PostgreSQL. Check BACKALOR_DATABASE_URL and database availability.') from None
            try:
                with connection.transaction(): yield PostgresConnection(connection)
            finally: connection.close()
            return
        db=sqlite3.connect(self.path,timeout=15)
        db.create_function('casefold',1,lambda value:value.casefold() if isinstance(value,str) else '')
        db.create_function('strpos',2,lambda value,query:value.find(query)+1)
        db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback();raise
        finally: db.close()
