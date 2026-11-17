"""Durability and access checks for a free API with no persistent filesystem."""
from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import test_api as api
from backend.config import Settings


class FreeHostingTests(unittest.TestCase):
    login=api.ApiTests.login
    flow=api.ApiTests.flow
    project=api.ApiTests.project
    tearDown=api.ApiTests.tearDown

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.settings=Settings(self.root,google_client_id='test',google_client_secret='test',max_upload_bytes=4096,snapshot_storage='database')
        self.app=api.create_app(self.settings)
        self.app.state.identity_provider=lambda *args:{'sub':'one','email':'one@example.com','name':'One'}
        self.client=TestClient(self.app);self.client.__enter__()

    def upload(self,project,headers,body=None):
        return self.client.put('/projects/'+project['id']+'/snapshot',headers={**headers,'If-Match':str(project['version'])},content=body or api.archive_bytes())

    def test_zip_persists_in_database_and_temporary_file_is_removed(self):
        owner=self.login();project=self.project(owner);body=api.archive_bytes()
        response=self.upload(project,owner,body);self.assertEqual(response.status_code,200,response.text)
        with self.app.state.database.connect() as db:
            row=db.execute('SELECT data FROM project_snapshots').fetchone()
            self.assertEqual(bytes(row['data']),body)
        self.assertEqual(list((self.root/'snapshots').iterdir()),[])
        self.assertEqual(self.client.get('/projects/'+project['id']+'/snapshot',headers=owner).content,body)

    def test_redeploy_with_empty_local_disk_keeps_the_snapshot(self):
        owner=self.login();project=self.project(owner);body=api.archive_bytes()
        self.assertEqual(self.upload(project,owner,body).status_code,200)
        shutil.rmtree(self.root/'snapshots')
        self.client.__exit__(None,None,None)
        self.app=api.create_app(self.app.state.settings)
        self.client=TestClient(self.app);self.client.__enter__()
        response=self.client.get('/projects/'+project['id']+'/snapshot',headers=owner)
        self.assertEqual(response.status_code,200);self.assertEqual(response.content,body)

    def test_updates_remove_old_blob_and_conflicts_preserve_latest(self):
        owner=self.login();project=self.project(owner)
        updated=self.upload(project,owner).json();body=api.archive_bytes(value=b'new scan')
        response=self.upload(updated,owner,body);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.upload(project,owner).status_code,409)
        with self.app.state.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM project_snapshots').fetchone()[0],1)
        self.assertEqual(self.client.get('/projects/'+project['id']+'/snapshot',headers=owner).content,body)

    def test_private_blob_cannot_be_downloaded_or_replaced_by_outsider(self):
        owner=self.login('owner');project=self.project(owner);self.upload(project,owner)
        outsider=self.login('outsider');path='/projects/'+project['id']+'/snapshot'
        self.assertEqual(self.client.get(path,headers=outsider).status_code,404)
        self.assertEqual(self.upload(project,outsider).status_code,404)

    def test_delete_removes_blob_and_project(self):
        owner=self.login();project=self.project(owner);self.upload(project,owner)
        self.assertEqual(self.client.delete('/projects/'+project['id'],headers=owner).status_code,204)
        with self.app.state.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM project_snapshots').fetchone()[0],0)
        self.assertEqual(self.client.get('/projects/'+project['id']+'/snapshot',headers=owner).status_code,404)

    def test_failed_database_write_keeps_previous_blob(self):
        from contextlib import contextmanager
        owner=self.login();project=self.project(owner);body=api.archive_bytes()
        updated=self.upload(project,owner,body).json()
        database=self.app.state.database;original=database.connect
        class Broken:
            def __init__(self,connection):self.connection=connection
            def execute(self,sql,params=None):
                if sql.startswith('UPDATE projects SET snapshot='):raise RuntimeError('simulated failure')
                return self.connection.execute(sql,params) if params is not None else self.connection.execute(sql)
        @contextmanager
        def broken():
            with original() as connection:yield Broken(connection)
        with patch.object(database,'connect',broken),self.assertRaises(RuntimeError):self.upload(updated,owner,api.archive_bytes(value=b'new'))
        with original() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM project_snapshots').fetchone()[0],1)
        self.assertEqual(self.client.get('/projects/'+project['id']+'/snapshot',headers=owner).content,body)
        self.assertEqual(list((self.root/'snapshots').iterdir()),[])

    def test_oversized_or_invalid_zip_leaves_no_blob(self):
        owner=self.login();project=self.project(owner)
        self.assertEqual(self.upload(project,owner,b'x'*4097).status_code,413)
        self.assertEqual(self.upload(project,owner,b'not a zip').status_code,422)
        with self.app.state.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM project_snapshots').fetchone()[0],0)
        self.assertEqual(list((self.root/'snapshots').iterdir()),[])

    def test_database_mode_rejects_unbounded_archive_size(self):
        with self.assertRaisesRegex(RuntimeError,'20 MiB'):
            api.create_app(replace(self.settings,data_dir=self.root/'oversized',max_upload_bytes=512*1024*1024))
