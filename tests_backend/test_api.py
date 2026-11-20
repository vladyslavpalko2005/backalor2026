from __future__ import annotations
import io
import json
import re
import secrets
import tempfile
import time
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.config import Settings
from backend.main import create_app,digest
from backend.google_login import exchange_code


def archive_bytes(name='images_raw/page.txt',value=b'scan'):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:archive.writestr(name,value)
    return buffer.getvalue()

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.settings=Settings(self.root,google_client_id='test.apps.googleusercontent.com',google_client_secret='test-secret',max_upload_bytes=4096)
        self.app=create_app(self.settings)
        self.app.state.identity_provider=lambda *args:{'sub':'google-user-one','email':'one@example.com','name':'One'}
        self.client=TestClient(self.app);self.client.__enter__()
    def tearDown(self):self.client.__exit__(None,None,None);self.temp.cleanup()
    def flow(self):
        result=self.client.post('/auth/google/start');self.assertEqual(result.status_code,200)
        flow=result.json();return {'state':flow['state'],'poll_secret':flow['poll_secret']},flow
    def login(self,sub='one'):
        self.app.state.identity_provider=lambda *args:{'sub':sub,'email':sub+'@example.com','name':sub}
        payload,flow=self.flow()
        response=self.client.get('/auth/google/callback',params={'state':payload['state'],'code':'google-test-code'})
        self.assertEqual(response.status_code,200)
        response=self.client.post('/auth/google/poll',json=payload)
        self.assertEqual(response.status_code,200)
        return {'Authorization':'Bearer '+response.json()['access_token']}
    def project(self,headers):
        response=self.client.post('/projects',json={'title':'Cipher key','description':'archive'},headers=headers)
        self.assertEqual(response.status_code,201,response.text);return response.json()
    def test_missing_configuration_is_actionable(self):
        app=create_app(Settings(self.root/'unconfigured'))
        with TestClient(app) as client:
            self.assertFalse(client.get('/health').json()['google_configured'])
            self.assertEqual(client.post('/auth/google/start').status_code,503)
    def test_authorization_url_uses_state_nonce_and_pkce(self):
        payload,flow=self.flow();query=parse_qs(urlsplit(flow['authorization_url']).query)
        self.assertEqual(query['scope'],['openid email profile'])
        self.assertEqual(query['redirect_uri'],[self.settings.redirect_uri])
        self.assertEqual(query['state'],[payload['state']]);self.assertIn('nonce',query)
        self.assertEqual(query['code_challenge_method'],['S256']);self.assertNotIn('client_secret',query)
        self.assertNotIn(payload['poll_secret'],flow['authorization_url'])
    def test_poll_requires_separate_secret(self):
        payload,_=self.flow()
        response=self.client.post('/auth/google/poll',json={**payload,'poll_secret':secrets.token_urlsafe(32)})
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.post('/auth/google/poll',json=payload).json(),{'status':'pending'})
    def test_callback_unknown_state_rejected(self):
        self.assertEqual(self.client.get('/auth/google/callback',params={'state':'wrong','code':'x'}).status_code,400)
    def test_callback_page_is_localized_and_keeps_oauth_secrets_private(self):
        payload,_=self.flow()
        response=self.client.get('/auth/google/callback',params={'state':payload['state'],'code':'private-google-code'},
                                 headers={'Accept-Language':'en;q=0,sk-SK;q=1,uk;q=0.5'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['content-language'],'sk')
        self.assertIn('<html lang="sk">',response.text)
        for secret in (payload['state'],payload['poll_secret'],'private-google-code','one@example.com'):
            self.assertNotIn(secret,response.text)
        policy=response.headers['content-security-policy']
        nonce=re.search(r"style-src 'nonce-([^']+)'",policy).group(1)
        self.assertIn(f'<style nonce="{nonce}">',response.text)
        self.assertIn(f'<script nonce="{nonce}">',response.text)
        self.assertIn(f"script-src 'nonce-{nonce}'",policy)
        self.assertNotIn('unsafe-inline',policy)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual(response.headers['referrer-policy'],'no-referrer')
        self.assertEqual(self.client.get('/health').headers['content-security-policy'],"default-src 'none'; frame-ancestors 'none'")
    def test_callback_and_token_delivery_are_single_use(self):
        payload,_=self.flow()
        self.assertEqual(self.client.get('/auth/google/callback',params={'state':payload['state'],'code':'x'}).status_code,200)
        self.assertEqual(self.client.get('/auth/google/callback',params={'state':payload['state'],'code':'x'}).status_code,400)
        first=self.client.post('/auth/google/poll',json=payload);self.assertIn('access_token',first.json())
        self.assertEqual(self.client.post('/auth/google/poll',json=payload).status_code,400)
        with self.app.state.database.connect() as db:
            row=db.execute('SELECT * FROM sessions').fetchone();self.assertNotEqual(row['token_hash'],first.json()['access_token'])
    def test_concurrent_poll_cannot_issue_two_sessions(self):
        payload,_=self.flow();self.client.get('/auth/google/callback',params={'state':payload['state'],'code':'x'})
        with ThreadPoolExecutor(2) as pool:responses=list(pool.map(lambda _:self.client.post('/auth/google/poll',json=payload),range(2)))
        self.assertEqual(sorted(r.status_code for r in responses),[200,400])
        with self.app.state.database.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],1)
    def test_expired_flow_is_rejected(self):
        payload,_=self.flow()
        with self.app.state.database.connect() as db:db.execute('UPDATE login_flows SET expires_at=0')
        self.assertEqual(self.client.post('/auth/google/poll',json=payload).status_code,400)
    def test_google_denial_and_invalid_identity_issue_no_session(self):
        payload,_=self.flow();self.client.get('/auth/google/callback',params={'state':payload['state'],'error':'access_denied'})
        self.assertEqual(self.client.post('/auth/google/poll',json=payload).json()['status'],'failed')
        payload,_=self.flow()
        def fail(*args):raise ValueError('untrusted Google token')
        self.app.state.identity_provider=fail
        self.assertEqual(self.client.get('/auth/google/callback',params={'state':payload['state'],'code':'bad'}).status_code,400)
        self.assertEqual(self.client.post('/auth/google/poll',json=payload).json()['status'],'failed')
        with self.app.state.database.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
    def test_cancel_invalidates_callback(self):
        payload,_=self.flow();self.assertEqual(self.client.post('/auth/google/cancel',json=payload).status_code,204)
        self.assertEqual(self.client.get('/auth/google/callback',params={'state':payload['state'],'code':'x'}).status_code,400)
    def test_google_sub_is_stable_identity(self):
        first=self.login('same');one=self.client.get('/auth/me',headers=first).json()['id']
        second=self.login('same');two=self.client.get('/auth/me',headers=second).json()['id']
        self.assertEqual(one,two)
    def test_protected_routes_require_session(self):
        self.assertEqual(self.client.get('/projects').status_code,401)
        self.assertEqual(self.client.post('/projects',json={'title':'x'}).status_code,401)
        self.assertEqual(self.client.get('/auth/me').status_code,401)
    def test_logout_revokes_session(self):
        headers=self.login();self.assertEqual(self.client.post('/auth/logout',headers=headers).status_code,204)
        self.assertEqual(self.client.get('/auth/me',headers=headers).status_code,401)
    def test_expired_session_rejected(self):
        headers=self.login()
        with self.app.state.database.connect() as db:db.execute('UPDATE sessions SET expires_at=0')
        self.assertEqual(self.client.get('/projects',headers=headers).status_code,401)
    def test_owner_isolation_on_every_project_route(self):
        one=self.login('one');project=self.project(one);two=self.login('two')
        self.assertEqual(self.client.get('/projects',headers=two).json(),[])
        for method,suffix in [('GET',''),('GET','/snapshot'),('DELETE',''),('PUT','/snapshot')]:
            response=self.client.request(method,'/projects/'+project['id']+suffix,headers={**two,'If-Match':'0'},content=archive_bytes() if method=='PUT' else None)
            self.assertEqual(response.status_code,404)
        self.assertEqual(len(self.client.get('/projects',headers=one).json()),1)
    def test_snapshot_roundtrip_version_conflict_and_delete(self):
        headers=self.login();project=self.project(headers);path='/projects/'+project['id'];body=archive_bytes()
        response=self.client.put(path+'/snapshot',headers={**headers,'If-Match':'0'},content=body)
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['version'],1)
        self.assertEqual(self.client.get(path+'/snapshot',headers=headers).content,body)
        self.assertEqual(self.client.put(path+'/snapshot',headers={**headers,'If-Match':'0'},content=body).status_code,409)
        self.assertEqual(self.client.get(path+'/snapshot',headers=headers).content,body)
        self.assertEqual(self.client.delete(path,headers=headers).status_code,204)
        self.assertEqual(self.client.get(path,headers=headers).status_code,404)
    def test_rejects_invalid_archives_and_traversal(self):
        headers=self.login();project=self.project(headers);path='/projects/'+project['id']+'/snapshot'
        for body in [b'not-zip',archive_bytes('../escape.txt'),archive_bytes('results/secrets.txt'),archive_bytes('/absolute')]:
            self.assertEqual(self.client.put(path,headers={**headers,'If-Match':'0'},content=body).status_code,422)
        self.assertEqual(self.client.get('/projects/'+project['id'],headers=headers).json()['version'],0)
        self.assertEqual(list((self.root/'snapshots').iterdir()),[])
    def test_upload_limit_and_required_version(self):
        headers=self.login();project=self.project(headers);path='/projects/'+project['id']+'/snapshot'
        self.assertEqual(self.client.put(path,headers={**headers,'If-Match':'0'},content=b'x'*4097).status_code,413)
        self.assertEqual(self.client.put(path,headers=headers,content=archive_bytes()).status_code,422)
    def test_sensitive_responses_disable_caching(self):
        response=self.client.post('/auth/google/start')
        self.assertEqual(response.headers['cache-control'],'no-store');self.assertEqual(response.headers['referrer-policy'],'no-referrer')
    def test_whitespace_title_rejected(self):
        self.assertEqual(self.client.post('/projects',headers=self.login(),json={'title':'   '}).status_code,422)

class GoogleValidationTests(unittest.TestCase):
    def setUp(self):self.settings=Settings(Path('/tmp/unused'),google_client_id='client',google_client_secret='secret')
    def exchange(self,claims):
        with patch('backend.google_login.requests.post') as post,patch('backend.google_login.id_token.verify_oauth2_token',return_value=claims) as verify:
            post.return_value.json.return_value={'id_token':'signed-token'}
            result=exchange_code(self.settings,'code','verifier','nonce')
            self.assertEqual(verify.call_args.args[2],'client')
            self.assertEqual(post.call_args.kwargs['data']['code_verifier'],'verifier')
            return result
    def test_valid_verified_google_claims(self):
        result=self.exchange({'sub':'subject','email':'a@example.com','email_verified':True,'iss':'https://accounts.google.com','nonce':'nonce'})
        self.assertEqual(result['sub'],'subject')
    def test_invalid_claims_rejected(self):
        valid={'sub':'subject','email':'a@example.com','email_verified':True,'iss':'https://accounts.google.com','nonce':'nonce'}
        for altered in ({'nonce':'bad'},{'iss':'https://evil.example'},{'email_verified':False},{'sub':''},{'azp':'other'}):
            with self.subTest(altered=altered),self.assertRaises(ValueError):self.exchange({**valid,**altered})

if __name__=='__main__':unittest.main()
