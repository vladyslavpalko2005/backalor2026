from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import unittest
import test_api as api
from backend.main import create_app
from backend.config import Settings
from backend.db import postgres_query


class CloudBackendTests(unittest.TestCase):
    setUp=api.ApiTests.setUp
    tearDown=api.ApiTests.tearDown
    login=api.ApiTests.login
    flow=api.ApiTests.flow
    project=api.ApiTests.project
    def test_readiness_checks_database_and_storage(self):
        response=self.client.get('/ready');self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['database'],'postgresql' if self.app.state.settings.database_url else 'sqlite')
        with patch.object(self.app.state.database,'connect',side_effect=RuntimeError('postgresql://user:SECRET@host/db')):
            response=self.client.get('/ready')
        self.assertEqual(response.status_code,503);self.assertNotIn('SECRET',response.text)
    def test_cloud_mode_refuses_sqlite_fallback(self):
        with self.assertRaisesRegex(RuntimeError,'PostgreSQL'):
            create_app(Settings(self.root/'missing-cloud-db',require_postgres=True))
        self.assertFalse((self.root/'missing-cloud-db/backalor.sqlite3').exists())
    def test_project_list_has_no_per_document_permission_query(self):
        owner=self.login('owner')
        for index in range(8):
            project=self.project(owner)
            response=self.client.patch('/projects/'+project['id'],headers={**owner,'If-Match':'0'},json={'title':f'Public {index}','visibility':'public'})
            self.assertEqual(response.status_code,200)
        outsider=self.login('reader');queries=[];database=self.app.state.database;original=database.connect
        class Tracked:
            def __init__(self,connection):self.connection=connection
            def execute(self,sql,params=None):
                queries.append(sql)
                return self.connection.execute(sql,params) if params is not None else self.connection.execute(sql)
        @contextmanager
        def tracked():
            with original() as connection:yield Tracked(connection)
        with patch.object(database,'connect',tracked):
            response=self.client.get('/projects',headers=outsider,params={'scope':'public'})
        self.assertEqual(len(response.json()),8)
        selects=[sql for sql in queries if sql.lstrip().upper().startswith('SELECT')]
        self.assertEqual(len(selects),2,selects)
        self.assertTrue(all(row['access_role']=='reader' for row in response.json()))
    def test_search_normalization_updates_with_metadata(self):
        owner=self.login();project=self.project(owner)
        self.client.patch('/projects/'+project['id'],headers={**owner,'If-Match':'0'},json={'title':'ŠIFRA Україна','description':'Výskum'})
        result=self.client.get('/projects',headers=owner,params={'q':'україна'}).json()
        self.assertEqual(result[0]['title'],'ŠIFRA Україна')
        self.assertEqual(len(self.client.get('/projects',headers=owner,params={'q':'VÝSKUM'}).json()),1)
    def test_postgres_parameters_preserve_literals(self):
        query="SELECT ':literal?', \"named?column\", :name WHERE id=?"
        self.assertEqual(postgres_query(query),"SELECT ':literal?', \"named?column\", %(name)s WHERE id=%s")
    def test_render_origin_does_not_require_a_hardcoded_hostname(self):
        import os
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as root,patch.dict(os.environ,{'BACKALOR_DATA_DIR':root,'RENDER_EXTERNAL_URL':'https://service.onrender.com','BACKALOR_DATABASE_URL':'postgresql://private/db','BACKALOR_REQUIRE_POSTGRES':'1','BACKALOR_PUBLIC_URL':''}):
            settings=Settings.from_env()
        self.assertEqual(settings.public_url,'https://service.onrender.com')
        self.assertEqual(settings.redirect_uri,'https://service.onrender.com/auth/google/callback')
    def test_connection_errors_do_not_expose_database_passwords(self):
        import psycopg
        from backend.db import Database
        with patch('psycopg.connect',side_effect=psycopg.OperationalError('SECRET')):
            with self.assertRaises(RuntimeError) as error:Database(url='postgresql://user:SECRET@host/db')
        self.assertNotIn('SECRET',str(error.exception))
    def test_migration_preserves_projects_and_skips_tokens(self):
        from types import SimpleNamespace
        from backend.db import Database
        from backend.migrate_postgres import migrate
        from test_api import archive_bytes
        source=Database(self.root/'legacy.sqlite3')
        with source.connect() as db:
            db.execute("INSERT INTO users VALUES ('owner','google-owner','a@example.org','Owner',1)")
            db.execute("INSERT INTO users VALUES ('reader','google-reader','b@example.org','Reader',1)")
            db.execute("INSERT INTO sessions VALUES ('do-not-copy','owner',999999999)")
            db.execute("INSERT INTO projects (id,owner_id,title,description,version,snapshot,created_at,updated_at) VALUES ('key','owner','Šifra','Архів',2,'scan.zip',1,2)")
            db.execute("INSERT INTO project_shares VALUES ('key','reader','reader')")
        source_snapshots=self.root/'old-snapshots';source_snapshots.mkdir();body=archive_bytes();(source_snapshots/'scan.zip').write_bytes(body)
        target=SimpleNamespace(url=self.app.state.settings.database_url or 'postgresql://test-adapter',connect=self.app.state.database.connect)
        result=migrate(source.path,source_snapshots,self.root/'snapshots',target)
        self.assertEqual(result,{'users':2,'projects':1,'shares':1,'snapshots':1})
        self.assertEqual((self.root/'snapshots/scan.zip').read_bytes(),body)
        with target.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
            project=db.execute("SELECT * FROM projects WHERE id='key'").fetchone()
            self.assertEqual((project['version'],project['visibility'],project['title_search']),(2,'private','šifra'))
        with self.assertRaisesRegex(ValueError,'empty'):migrate(source.path,source_snapshots,self.root/'snapshots',target)
    def test_migration_missing_source_files_does_not_write_records(self):
        from types import SimpleNamespace
        from backend.db import Database
        from backend.migrate_postgres import migrate
        source=Database(self.root/'missing-source.sqlite3')
        with source.connect() as db:
            db.execute("INSERT INTO users VALUES ('owner','google-owner','a@example.org','Owner',1)")
            db.execute("INSERT INTO projects (id,owner_id,title,version,snapshot,created_at,updated_at) VALUES ('key','owner','Title',1,'missing.zip',1,2)")
        target=SimpleNamespace(url=self.app.state.settings.database_url or 'postgresql://test-adapter',connect=self.app.state.database.connect)
        with self.assertRaises(ValueError):migrate(source.path,self.root/'none',self.root/'snapshots',target)
        with target.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],0)
    def test_migration_rolls_back_database_and_created_archives_on_failure(self):
        from contextlib import contextmanager
        from types import SimpleNamespace
        from backend.db import Database
        from backend.migrate_postgres import migrate
        from test_api import archive_bytes
        source=Database(self.root/'rollback-source.sqlite3')
        with source.connect() as db:
            db.execute("INSERT INTO users VALUES ('owner','google-owner','a@example.org','Owner',1)")
            db.execute("INSERT INTO projects (id,owner_id,title,version,snapshot,created_at,updated_at) VALUES ('key','owner','Title',1,'new.zip',1,2)")
            db.execute("INSERT INTO project_shares VALUES ('key','owner','reader')")
        folder=self.root/'rollback-archives';folder.mkdir();(folder/'new.zip').write_bytes(archive_bytes())
        class Failing:
            def __init__(self,connection):self.connection=connection
            def execute(self,sql,params=None):
                if sql.startswith('INSERT INTO project_shares'):raise RuntimeError('Simulated write failure')
                return self.connection.execute(sql,params) if params is not None else self.connection.execute(sql)
        @contextmanager
        def connect():
            with self.app.state.database.connect() as db:yield Failing(db)
        target=SimpleNamespace(url=self.app.state.settings.database_url or 'postgresql://test-adapter',connect=connect)
        with self.assertRaises(RuntimeError):migrate(source.path,folder,self.root/'snapshots',target)
        self.assertFalse((self.root/'snapshots/new.zip').exists())
        with self.app.state.database.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],0)
