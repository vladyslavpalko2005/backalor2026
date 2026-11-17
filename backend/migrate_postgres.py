"""One-time migration of a stopped local server into an empty cloud PostgreSQL DB.

Tokens and pending OAuth flows are intentionally not migrated. Database secrets
are read from server environment variables, never command-line arguments.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import shutil
import sqlite3
from .archives import validate_archive
from .config import Settings
from .db import Database


def migrate(source,source_snapshots,target_snapshots,database,snapshot_storage='filesystem',max_upload_bytes=20*1024*1024):
    if not database.url:raise ValueError('Migration requires a PostgreSQL target')
    if snapshot_storage not in ('filesystem','database'):raise ValueError('Unknown snapshot storage mode')
    source=Path(source);source_snapshots=Path(source_snapshots);target_snapshots=Path(target_snapshots)
    connection=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True);connection.row_factory=sqlite3.Row
    try:
        connection.execute('BEGIN')
        tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'users','projects'}<=tables:raise ValueError('Not a Backalor server database')
        users=[dict(row) for row in connection.execute('SELECT * FROM users')]
        projects=[dict(row) for row in connection.execute('SELECT * FROM projects')]
        shares=[dict(row) for row in connection.execute('SELECT * FROM project_shares')] if 'project_shares' in tables else []
    finally:connection.close()
    snapshots={project['snapshot'] for project in projects if project.get('snapshot')}
    for name in snapshots:
        if Path(name).name!=name or not name.endswith('.zip'):raise ValueError('Invalid source snapshot name')
        path=source_snapshots/name
        if path.is_symlink() or not path.is_file() or path.resolve().parent!=source_snapshots.resolve():raise ValueError('A source snapshot is missing or outside its directory')
        validate_archive(path)
        if snapshot_storage=='database' and path.stat().st_size>max_upload_bytes:
            raise ValueError('Source archive exceeds database snapshot limit; split the project before migrating')
    copied=[]
    try:
        with database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for table in ('users','projects','sessions','login_flows','project_shares','project_snapshots'):
                if db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:raise ValueError('Target database must be empty; no data was overwritten')
            target_snapshots.mkdir(parents=True,exist_ok=True)
            for name in sorted(snapshots):
                if snapshot_storage=='database':
                    db.execute('INSERT INTO project_snapshots (name,data) VALUES (?,?)',(name,(source_snapshots/name).read_bytes()))
                    continue
                destination=target_snapshots/name
                with destination.open('xb') as output:
                    copied.append(destination)
                    with (source_snapshots/name).open('rb') as input_stream:shutil.copyfileobj(input_stream,output)
                    output.flush();os.fsync(output.fileno())
            for user in users:
                db.execute('INSERT INTO users (id,google_sub,email,name,created_at) VALUES (?,?,?,?,?)',tuple(user[key] for key in ('id','google_sub','email','name','created_at')))
            for project in projects:
                db.execute('INSERT INTO projects (id,owner_id,title,description,version,snapshot,created_at,updated_at,visibility,title_search,description_search) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           tuple(project[key] for key in ('id','owner_id','title','description','version','snapshot','created_at','updated_at'))+
                           (project.get('visibility','private'),project['title'].casefold(),project['description'].casefold()))
            for share in shares:
                db.execute('INSERT INTO project_shares (project_id,user_id,role) VALUES (?,?,?)',tuple(share[key] for key in ('project_id','user_id','role')))
    except BaseException:
        for destination in copied:destination.unlink(missing_ok=True)
        raise
    return {'users':len(users),'projects':len(projects),'shares':len(shares),'snapshots':len(snapshots)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--source-snapshots',type=Path,required=True)
    parser.add_argument('--target-snapshots',type=Path,required=True)
    args=parser.parse_args();settings=Settings.from_env()
    if not settings.database_url:parser.error('Set BACKALOR_DATABASE_URL to an empty cloud PostgreSQL database')
    result=migrate(args.source,args.source_snapshots,args.target_snapshots,Database(url=settings.database_url),snapshot_storage=settings.snapshot_storage,max_upload_bytes=settings.max_upload_bytes)
    print(result)


if __name__=='__main__':main()
