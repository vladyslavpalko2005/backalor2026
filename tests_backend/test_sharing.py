from __future__ import annotations
import io
import sqlite3
import time
import unittest
import zipfile
import test_api as api
from test_api import archive_bytes
from backend.db import Database


class SharingTests(unittest.TestCase):
    setUp = api.ApiTests.setUp
    tearDown = api.ApiTests.tearDown
    login = api.ApiTests.login
    flow = api.ApiTests.flow
    project = api.ApiTests.project

    def prepare(self):
        owner = self.login('owner'); project = self.project(owner)
        reader = self.login('reader'); outsider = self.login('outsider')
        return owner, reader, outsider, project

    def publish(self, project, owner, visibility='public'):
        return self.client.patch('/projects/'+project['id'], headers={**owner,'If-Match':str(project['version'])},
                                 json={'title':'Історичний ключ','description':'ARCHIVE Bratislava','visibility':visibility})

    def test_existing_projects_migrate_privately_and_preserve_snapshot(self):
        path = self.root/'legacy.sqlite3'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE projects (id TEXT PRIMARY KEY,owner_id TEXT,title TEXT,description TEXT,version INTEGER,snapshot TEXT,created_at INTEGER,updated_at INTEGER)')
            db.execute("INSERT INTO projects VALUES ('project','owner','Title','Description',3,'scan.zip',1,2)")
        database = Database(path)
        with database.connect() as db:
            row = db.execute('SELECT * FROM projects').fetchone()
            self.assertEqual((row['visibility'],row['version'],row['snapshot']),('private',3,'scan.zip'))
        Database(path)  # Restart is idempotent.

    def test_private_projects_are_absent_in_every_outsider_scope(self):
        owner, reader, outsider, project = self.prepare()
        for scope in ('mine','shared','all','public'):
            self.assertEqual(self.client.get('/projects',headers=outsider,params={'scope':scope}).json(),[])
        self.assertEqual(self.client.get('/projects/'+project['id'],headers=outsider).status_code,404)

    def test_public_read_and_private_retraction(self):
        owner, reader, outsider, project = self.prepare()
        body = archive_bytes()
        self.client.put('/projects/'+project['id']+'/snapshot',headers={**owner,'If-Match':'0'},content=body)
        project = self.client.get('/projects/'+project['id'],headers=owner).json()
        response = self.publish(project,owner); self.assertEqual(response.status_code,200,response.text)
        project = response.json()
        self.assertEqual(self.client.get('/projects',headers=outsider,params={'scope':'public'}).json()[0]['access_role'],'reader')
        self.assertEqual(self.client.get('/projects/'+project['id']+'/snapshot',headers=outsider).content,body)
        self.assertEqual(self.client.put('/projects/'+project['id']+'/snapshot',headers={**outsider,'If-Match':str(project['version'])},content=body).status_code,403)
        self.assertEqual(self.client.delete('/projects/'+project['id'],headers=outsider).status_code,404)
        self.assertEqual(self.publish(project,owner,'private').status_code,200)
        self.assertEqual(self.client.get('/projects/'+project['id']+'/snapshot',headers=outsider).status_code,404)

    def test_reader_editor_and_revocation(self):
        owner, reader, outsider, project = self.prepare(); path='/projects/'+project['id']
        share = self.client.put(path+'/shares',headers=owner,json={'email':'READER@example.com','role':'reader'})
        self.assertEqual(share.status_code,200,share.text)
        user_id = share.json()['user_id']
        listed = self.client.get('/projects',headers=reader,params={'scope':'shared'}).json()
        self.assertEqual(listed[0]['access_role'],'reader')
        self.assertEqual(self.client.get('/projects',headers=reader).json(),[])
        body=archive_bytes()
        self.assertEqual(self.client.put(path+'/snapshot',headers={**reader,'If-Match':'0'},content=body).status_code,403)
        self.assertEqual(self.client.put(path+'/shares',headers=owner,json={'email':'reader@example.com','role':'editor'}).status_code,200)
        response=self.client.put(path+'/snapshot',headers={**reader,'If-Match':'0'},content=body)
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['access_role'],'editor')
        self.assertEqual(self.client.get(path+'/snapshot',headers=reader).content,body)
        self.assertEqual(self.client.get('/projects',headers=outsider,params={'scope':'all'}).json(),[])
        self.assertEqual(self.client.delete(path+'/shares/'+user_id,headers=owner).status_code,204)
        self.assertEqual(self.client.get(path,headers=reader).status_code,404)
        self.assertEqual(self.client.get('/projects',headers=reader,params={'scope':'shared'}).json(),[])

    def test_only_owner_manages_metadata_and_invitations(self):
        owner, reader, outsider, project=self.prepare();path='/projects/'+project['id']
        self.client.put(path+'/shares',headers=owner,json={'email':'reader@example.com','role':'editor'})
        for headers in (reader,outsider):
            self.assertEqual(self.client.get(path+'/shares',headers=headers).status_code,404)
            self.assertEqual(self.client.put(path+'/shares',headers=headers,json={'email':'outsider@example.com'}).status_code,404)
            self.assertEqual(self.client.delete(path+'/shares/anything',headers=headers).status_code,404)
            self.assertEqual(self.publish(project,headers).status_code,404)
            self.assertEqual(self.client.delete(path,headers=headers).status_code,404)
        self.assertEqual(len(self.client.get(path+'/shares',headers=owner).json()),1)

    def test_bad_invitation_and_version_conflicts(self):
        owner, reader, outsider, project=self.prepare();path='/projects/'+project['id']
        for email,role,status in [('unknown@example.com','reader',404),('owner@example.com','reader',422),('reader@example.com','owner',422)]:
            response=self.client.put(path+'/shares',headers=owner,json={'email':email,'role':role})
            self.assertEqual(response.status_code,status,response.text)
        first=self.publish(project,owner);self.assertEqual(first.status_code,200)
        self.assertEqual(self.publish(project,owner).status_code,409)
        self.assertEqual(self.client.put(path+'/snapshot',headers={**owner,'If-Match':'0'},content=archive_bytes()).status_code,409)

    def test_search_filters_unicode_pagination_and_access_control(self):
        owner,reader,outsider,project=self.prepare();self.publish(project,owner)
        # Additional private project must not leak through the global query.
        private=self.client.post('/projects',headers=owner,json={'title':'Історичний прихований'}).json()
        response=self.client.get('/projects',headers=outsider,params={'scope':'all','q':'ІСТОРИЧНИЙ'})
        self.assertEqual([entry['id'] for entry in response.json()],[project['id']])
        self.assertEqual(len(self.client.get('/projects',headers=outsider,params={'scope':'public','q':'bratislava'}).json()),1)
        self.assertEqual(self.client.get('/projects',headers=outsider,params={'scope':'public','visibility':'private'}).json(),[])
        self.assertEqual(self.client.get('/projects',headers=outsider,params={'scope':'public','has_snapshot':True}).json(),[])
        self.assertEqual(len(self.client.get('/projects',headers=owner,params={'scope':'mine','has_snapshot':False}).json()),2)
        first=self.client.get('/projects',headers=owner,params={'limit':1,'sort':'title'}).json()
        second=self.client.get('/projects',headers=owner,params={'limit':1,'sort':'title','offset':1}).json()
        self.assertEqual(len(first),1);self.assertNotEqual(first[0]['id'],second[0]['id'])
        self.assertEqual(self.client.get('/projects',headers=owner,params={'q':'%'}).json(),[])
        self.assertEqual(self.client.get('/projects',headers=owner,params={'scope':'secret'}).status_code,422)

    def test_new_routes_require_sign_in(self):
        for method,path,payload in [('GET','/projects?scope=public',None),('PATCH','/projects/id',{'title':'x'}),('GET','/projects/id/shares',None),('PUT','/projects/id/shares',{'email':'a@b.com'}),('DELETE','/projects/id/shares/u',None)]:
            self.assertEqual(self.client.request(method,path,json=payload,headers={'If-Match':'0'}).status_code,401)

    def test_delete_removes_shares_and_portable_library_is_uploadable(self):
        owner,reader,outsider,project=self.prepare();path='/projects/'+project['id']
        self.client.put(path+'/shares',headers=owner,json={'email':'reader@example.com'})
        body=archive_bytes('results/cipher_library.json',b'{"schema_version":1,"entries":[]}')
        self.assertEqual(self.client.put(path+'/snapshot',headers={**owner,'If-Match':'0'},content=body).status_code,200)
        self.assertEqual(self.client.delete(path,headers=owner).status_code,204)
        with self.app.state.database.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM project_shares').fetchone()[0],0)
