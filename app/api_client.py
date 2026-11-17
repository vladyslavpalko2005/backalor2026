"""Desktop bearer API client. Persistent credentials belong to the OS-backed session store, never project files."""
from __future__ import annotations
from pathlib import Path
from urllib.parse import urlsplit
import requests

class ApiError(RuntimeError):
    def __init__(self,message,status=None):super().__init__(message);self.status=status


def normalize_server_url(value):
    value=value.strip().rstrip('/')
    url=urlsplit(value)
    if url.scheme not in ('http','https') or not url.netloc or url.path or url.query or url.fragment or url.username or url.password:
        raise ValueError('Use a server origin such as http://127.0.0.1:8000 or https://api.example.com')
    if url.scheme=='http' and url.hostname not in ('127.0.0.1','localhost','::1'):
        raise ValueError('A remote backend must use HTTPS')
    return value


class ApiClient:
    def __init__(self,base_url='http://127.0.0.1:8000'):
        self.base_url=normalize_server_url(base_url);self.token=None;self.profile=None;self.on_auth_expired=None

    def request(self,method,path,**kwargs):
        headers=kwargs.pop('headers',{})
        if self.token:headers['Authorization']='Bearer '+self.token
        try:
            response=requests.request(method,self.base_url+path,headers=headers,timeout=kwargs.pop('timeout',(5,60)),allow_redirects=False,**kwargs)
        except requests.RequestException as exc:
            raise ApiError('Cannot connect to the backend. Check the address and start the server.') from exc
        if response.status_code>=300:
            try:detail=response.json().get('detail','Request failed')
            except (ValueError,AttributeError):detail='Request failed'
            if not isinstance(detail,str):detail='Invalid request data'
            if response.status_code==401:
                self.token=None;self.profile=None
                if callable(self.on_auth_expired):self.on_auth_expired()
            response.close()
            raise ApiError(detail,response.status_code)
        return response

    def json(self,method,path,**kwargs):
        with self.request(method,path,**kwargs) as response:
            return response.json() if response.content else None

    def start_login(self):return self.json('POST','/auth/google/start')
    def poll_login(self,flow):
        result=self.json('POST','/auth/google/poll',json={'state':flow['state'],'poll_secret':flow['poll_secret']})
        if result['status']=='authenticated':
            self.token=result['access_token']
            try:self.profile=self.json('GET','/auth/me')
            except Exception:self.token=None;raise
        return result
    def cancel_login(self,flow):
        self.json('POST','/auth/google/cancel',json={'state':flow['state'],'poll_secret':flow['poll_secret']})
    def logout(self):
        # Do not pretend that the server session was revoked if the request failed.
        self.json('POST','/auth/logout');self.token=None;self.profile=None
    def projects(self,**filters):return self.json('GET','/projects',params=filters) if filters else self.json('GET','/projects')
    def update_project(self,project,title,description,visibility):
        return self.json('PATCH',f"/projects/{project['id']}",json={'title':title,'description':description,'visibility':visibility},headers={'If-Match':str(project['version'])})
    def shares(self,project):return self.json('GET',f"/projects/{project['id']}/shares")
    def share(self,project,email,role):return self.json('PUT',f"/projects/{project['id']}/shares",json={'email':email,'role':role})
    def revoke_share(self,project,user_id):return self.json('DELETE',f"/projects/{project['id']}/shares/{user_id}")
    def create_project(self,title,description=''):return self.json('POST','/projects',json={'title':title,'description':description})
    def upload(self,project,source):
        with Path(source).open('rb') as stream:
            return self.json('PUT',f"/projects/{project['id']}/snapshot",data=stream,
                             headers={'Content-Type':'application/zip','If-Match':str(project['version'])})
    def download(self,project,target):
        with self.request('GET',f"/projects/{project['id']}/snapshot",stream=True) as response:
            with Path(target).open('wb') as stream:
                size=0
                for chunk in response.iter_content(1024*1024):
                    size+=len(chunk)
                    if size>512*1024*1024:raise ApiError('Snapshot exceeds 512 MiB')
                    stream.write(chunk)
