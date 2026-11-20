from __future__ import annotations
import base64
import hashlib
import os
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode
from typing import Optional, Literal
from fastapi import FastAPI, Depends, Header, HTTPException, Request, Response, Query
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from .config import Settings
from .db import Database
from .google_login import exchange_code
from .auth_page import google_callback_page
from .archives import validate_archive


def digest(value):return hashlib.sha256(value.encode()).hexdigest()

class PollInput(BaseModel):
    state: str = Field(min_length=32,max_length=128)
    poll_secret: str = Field(min_length=32,max_length=128)

class ProjectInput(BaseModel):
    title: str = Field(min_length=1,max_length=200)
    description: str = Field(default='',max_length=4000)


class ProjectUpdate(ProjectInput):
    visibility: Literal['private', 'public'] = 'private'

class ShareInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Literal['reader', 'editor'] = 'reader'


def create_app(settings=None):
    settings=settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True,exist_ok=True)
    if settings.require_postgres and not settings.database_url:
        raise RuntimeError('Cloud mode requires PostgreSQL; local SQLite is disabled')
    if settings.snapshot_storage not in ('filesystem','database'):
        raise RuntimeError('Unknown snapshot storage mode')
    if settings.snapshot_storage=='database' and settings.max_upload_bytes>20*1024*1024:
        raise RuntimeError('Database snapshots require max_upload_bytes <= 20 MiB')
    database=Database(settings.data_dir/'backalor.sqlite3',url=settings.database_url)
    snapshots=settings.data_dir/'snapshots';snapshots.mkdir(exist_ok=True)
    app=FastAPI(title='Backalor API',version='1.0.0')
    app.state.settings=settings;app.state.database=database
    app.state.identity_provider=exchange_code
    database_snapshots=settings.snapshot_storage=='database'

    @app.middleware('http')
    async def response_headers(request,call_next):
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers.setdefault('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'")
        return response

    def user(authorization: Optional[str]=Header(default=None)):
        if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'Sign in required')
        token=authorization[7:]
        if not 32<=len(token)<=128:raise HTTPException(401,'Invalid session')
        with database.connect() as db:
            record=db.execute('SELECT u.id,u.email,u.name FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?',
                              (digest(token),int(time.time()))).fetchone()
        if not record:raise HTTPException(401,'Session expired. Sign in again.')
        return dict(record)

    def owned_project(db,project_id,user_id):
        row=db.execute('SELECT * FROM projects WHERE id=? AND owner_id=?',(project_id,user_id)).fetchone()
        if row is None:raise HTTPException(404,'Project not found')
        return row

    def access_role(db,row,user_id):
        if row['owner_id']==user_id:return 'owner'
        share=db.execute('SELECT role FROM project_shares WHERE project_id=? AND user_id=?',(row['id'],user_id)).fetchone()
        if share:return share['role']
        return 'reader' if row['visibility']=='public' else None

    def accessible_project(db,project_id,user_id,write=False):
        row=db.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone()
        role=access_role(db,row,user_id) if row else None
        if role is None:raise HTTPException(404,'Project not found')
        if write and role not in ('owner','editor'):raise HTTPException(403,'This project is read-only')
        return row

    def project_view(row,role='owner'):
        return {key:row[key] for key in ('id','owner_id','title','description','version','visibility','created_at','updated_at')} | {'has_snapshot':bool(row['snapshot']), 'access_role':role}


    @app.get('/health')
    def health():return {'service':'backalor','status':'ok','google_configured':bool(settings.google_client_id and settings.google_client_secret)}

    @app.get('/ready')
    def ready():
        try:
            with database.connect() as db:db.execute('SELECT 1').fetchone()
            if not os.access(snapshots,os.W_OK):raise OSError('Snapshot storage unavailable')
        except Exception:raise HTTPException(503,'Database or snapshot storage is unavailable') from None
        return {'status':'ok','database':'postgresql' if settings.database_url else 'sqlite'}

    @app.post('/auth/google/start')
    def start():
        if not settings.google_client_id or not settings.google_client_secret:
            raise HTTPException(503,'Configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET on the backend first.')
        now=int(time.time());state=secrets.token_urlsafe(32);poll=secrets.token_urlsafe(32)
        nonce=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
        with database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_flows WHERE expires_at<=?',(now,))
            db.execute('DELETE FROM sessions WHERE expires_at<=?',(now,))
            if db.execute('SELECT count(*) FROM login_flows').fetchone()[0]>=200:raise HTTPException(429,'Too many pending sign-ins. Try later.')
            db.execute('INSERT INTO login_flows VALUES (?,?,?,?,?,?,?)',(digest(state),digest(poll),nonce,verifier,'pending',None,now+300))
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        url='https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({
            'client_id':settings.google_client_id,'redirect_uri':settings.redirect_uri,'response_type':'code',
            'scope':'openid email profile','state':state,'nonce':nonce,'code_challenge':challenge,
            'code_challenge_method':'S256','prompt':'select_account'})
        return {'authorization_url':url,'state':state,'poll_secret':poll,'expires_in':300,'interval':2}

    @app.get('/auth/google/callback',response_class=HTMLResponse)
    def callback(request: Request,state: str='',code: str='',error: str=''):
        language=request.headers.get('accept-language','')
        now=int(time.time())
        with database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            flow=db.execute('SELECT * FROM login_flows WHERE state_hash=?',(digest(state),)).fetchone()
            if not flow or flow['expires_at']<=now or flow['status']!='pending':
                return google_callback_page('inactive',language)
            db.execute('UPDATE login_flows SET status=? WHERE state_hash=?',('failed' if error or not code else 'exchanging',digest(state)))
        if error or not code:
            return google_callback_page('cancelled',language)
        try:
            identity=app.state.identity_provider(settings,code,flow['verifier'],flow['nonce'])
            with database.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                # Bind identity by Google's stable subject, never by a client-supplied email.
                existing=db.execute('SELECT id FROM users WHERE google_sub=?',(identity['sub'],)).fetchone()
                user_id=existing['id'] if existing else str(uuid.uuid4())
                db.execute('INSERT INTO users VALUES (?,?,?,?,?) ON CONFLICT(google_sub) DO UPDATE SET email=excluded.email,name=excluded.name',
                           (user_id,identity['sub'],identity['email'],identity['name'],now))
                db.execute('UPDATE login_flows SET status=?,user_id=? WHERE state_hash=? AND status=?',('ready',user_id,digest(state),'exchanging'))
        except Exception:
            with database.connect() as db:db.execute('UPDATE login_flows SET status=? WHERE state_hash=?',('failed',digest(state)))
            return google_callback_page('failed',language)
        return google_callback_page('success',language)

    @app.post('/auth/google/poll')
    def poll(payload: PollInput):
        now=int(time.time())
        with database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            flow=db.execute('SELECT * FROM login_flows WHERE state_hash=?',(digest(payload.state),)).fetchone()
            if not flow or flow['expires_at']<=now or not secrets.compare_digest(flow['poll_hash'],digest(payload.poll_secret)):
                raise HTTPException(400,'Invalid or expired sign-in request')
            if flow['status'] in ('pending','exchanging'):return {'status':'pending'}
            if flow['status']=='failed':return {'status':'failed'}
            if flow['status']!='ready':raise HTTPException(400,'This sign-in request was already consumed')
            token=secrets.token_urlsafe(48)
            db.execute('INSERT INTO sessions VALUES (?,?,?)',(digest(token),flow['user_id'],now+settings.session_seconds))
            db.execute('UPDATE login_flows SET status=?,verifier=?,nonce=? WHERE state_hash=?',('consumed','','',digest(payload.state)))
        return {'status':'authenticated','access_token':token,'token_type':'Bearer','expires_in':settings.session_seconds}

    @app.post('/auth/google/cancel',status_code=204)
    def cancel(payload: PollInput):
        with database.connect() as db:
            db.execute('DELETE FROM login_flows WHERE state_hash=? AND poll_hash=?',(digest(payload.state),digest(payload.poll_secret)))
        return Response(status_code=204)

    @app.get('/auth/me')
    def me(current=Depends(user)):return current

    @app.post('/auth/logout',status_code=204)
    def logout(authorization: str=Header(),current=Depends(user)):
        with database.connect() as db:db.execute('DELETE FROM sessions WHERE token_hash=?',(digest(authorization[7:]),))
        return Response(status_code=204)

    @app.get('/projects')
    def list_projects(current=Depends(user), scope:Literal['mine','public','shared','all']='mine',
                      q:str=Query(default='',max_length=200), visibility:Optional[Literal['private','public']]=None,
                      has_snapshot:Optional[bool]=None, sort:Literal['updated','title']='updated',
                      limit:int=Query(default=100,ge=1,le=500), offset:int=Query(default=0,ge=0)):
        conditions={
            'mine':'p.owner_id=:user_id',
            'public':"p.visibility='public'",
            'shared':'s.user_id IS NOT NULL AND p.owner_id!=:user_id',
            'all':"(p.owner_id=:user_id OR p.visibility='public' OR s.user_id IS NOT NULL)"}
        clauses=[conditions[scope]];params={'user_id':current['id'],'limit':limit,'offset':offset}
        if q.strip():
            clauses.append('(strpos(p.title_search,:q)>0 OR strpos(p.description_search,:q)>0)');params['q']=q.strip().casefold()
        if visibility:clauses.append('p.visibility=:visibility');params['visibility']=visibility
        if has_snapshot is not None:clauses.append('p.snapshot IS '+('NOT NULL' if has_snapshot else 'NULL'))
        order='p.title_search,p.id' if sort=='title' else 'p.updated_at DESC,p.id'
        sql="SELECT p.*,CASE WHEN p.owner_id=:user_id THEN 'owner' ELSE COALESCE(s.role,'reader') END AS access_role FROM projects p LEFT JOIN project_shares s ON s.project_id=p.id AND s.user_id=:user_id WHERE "+' AND '.join(clauses)+' ORDER BY '+order+' LIMIT :limit OFFSET :offset'
        with database.connect() as db:
            return [project_view(row,row['access_role']) for row in db.execute(sql,params).fetchall()]

    @app.post('/projects',status_code=201)
    def create_project(payload:ProjectInput,current=Depends(user)):
        if not payload.title.strip():raise HTTPException(422,'Project title is required')
        now=int(time.time());project_id=str(uuid.uuid4())
        with database.connect() as db:
            db.execute('INSERT INTO projects (id,owner_id,title,description,version,snapshot,created_at,updated_at,title_search,description_search) VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (project_id,current['id'],payload.title.strip(),payload.description,0,None,now,now,payload.title.strip().casefold(),payload.description.casefold()))
            return project_view(owned_project(db,project_id,current['id']))

    @app.get('/projects/{project_id}')
    def get_project(project_id:str,current=Depends(user)):
        with database.connect() as db:
            row=accessible_project(db,project_id,current['id'])
            return project_view(row,access_role(db,row,current['id']))

    @app.patch('/projects/{project_id}')
    def update_project(project_id:str,payload:ProjectUpdate,if_match:str=Header(),current=Depends(user)):
        if not payload.title.strip():raise HTTPException(422,'Project title is required')
        try:version=int(if_match.strip('"'))
        except ValueError:raise HTTPException(400,'If-Match must contain the project version')
        with database.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=owned_project(db,project_id,current['id'])
            if row['version']!=version:raise HTTPException(409,'Project changed on server. Refresh before updating.')
            db.execute('UPDATE projects SET title=?,description=?,visibility=?,version=version+1,updated_at=?,title_search=?,description_search=? WHERE id=?',
                       (payload.title.strip(),payload.description,payload.visibility,int(time.time()),payload.title.strip().casefold(),payload.description.casefold(),project_id))
            return project_view(owned_project(db,project_id,current['id']))

    @app.get('/projects/{project_id}/shares')
    def list_shares(project_id:str,current=Depends(user)):
        with database.connect() as db:
            owned_project(db,project_id,current['id'])
            return [dict(row) for row in db.execute('SELECT u.id AS user_id,u.email,u.name,s.role FROM project_shares s JOIN users u ON u.id=s.user_id WHERE s.project_id=? ORDER BY u.email',(project_id,))]

    @app.put('/projects/{project_id}/shares')
    def share_project(project_id:str,payload:ShareInput,current=Depends(user)):
        with database.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=owned_project(db,project_id,current['id'])
            target=db.execute('SELECT id FROM users WHERE lower(email)=lower(?)',(payload.email.strip(),)).fetchall()
            if not target:raise HTTPException(404,'Recipient must sign in to Backalor first')
            if len(target)!=1:raise HTTPException(409,'Recipient email is ambiguous')
            if target[0]['id']==current['id']:raise HTTPException(422,'Owner already has full access')
            count=db.execute('SELECT count(*) FROM project_shares WHERE project_id=?',(project_id,)).fetchone()[0]
            exists=db.execute('SELECT 1 FROM project_shares WHERE project_id=? AND user_id=?',(project_id,target[0]['id'])).fetchone()
            if count>=100 and not exists:raise HTTPException(422,'Project share limit reached')
            db.execute('INSERT INTO project_shares VALUES (?,?,?) ON CONFLICT(project_id,user_id) DO UPDATE SET role=excluded.role',(project_id,target[0]['id'],payload.role))
        return {'user_id':target[0]['id'],'role':payload.role}

    @app.delete('/projects/{project_id}/shares/{user_id}',status_code=204)
    def revoke_share(project_id:str,user_id:str,current=Depends(user)):
        with database.connect() as db:
            db.execute('BEGIN IMMEDIATE');owned_project(db,project_id,current['id'])
            db.execute('DELETE FROM project_shares WHERE project_id=? AND user_id=?',(project_id,user_id))
        return Response(status_code=204)

    @app.put('/projects/{project_id}/snapshot')
    async def upload(project_id:str,request:Request,if_match: str=Header(),current=Depends(user)):
        try:version=int(if_match.strip('"'))
        except ValueError:raise HTTPException(400,'If-Match must contain the project version')
        with database.connect() as db:
            record=accessible_project(db,project_id,current['id'],write=True)
            if record['version']!=version:raise HTTPException(409,'Project changed on server. Refresh before uploading.')
        path=snapshots/(str(uuid.uuid4())+'.zip');size=0
        try:
            with path.open('xb') as stream:
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>settings.max_upload_bytes:raise HTTPException(413,'Project archive exceeds upload limit')
                    await run_in_threadpool(stream.write,chunk)
                await run_in_threadpool(stream.flush)
                await run_in_threadpool(os.fsync,stream.fileno())
            try:await run_in_threadpool(validate_archive,path)
            except Exception:raise HTTPException(422,'Invalid project ZIP archive')
            archive_data=await run_in_threadpool(path.read_bytes) if database_snapshots else None
            with database.connect() as db:
                db.execute('BEGIN IMMEDIATE');record=accessible_project(db,project_id,current['id'],write=True)
                if record['version']!=version:raise HTTPException(409,'Project changed on server. Refresh before uploading.')
                old=record['snapshot']
                if database_snapshots:
                    db.execute('INSERT INTO project_snapshots (name,data) VALUES (?,?)',(path.name,archive_data))
                    if old:db.execute('DELETE FROM project_snapshots WHERE name=?',(old,))
                db.execute('UPDATE projects SET snapshot=?,version=version+1,updated_at=? WHERE id=?',(path.name,int(time.time()),project_id))
                result=project_view(accessible_project(db,project_id,current['id']),access_role(db,record,current['id']))
        except BaseException:
            path.unlink(missing_ok=True);raise
        if database_snapshots:path.unlink(missing_ok=True)
        if old:(snapshots/old).unlink(missing_ok=True)
        return result

    @app.get('/projects/{project_id}/snapshot')
    def download(project_id:str,current=Depends(user)):
        with database.connect() as db:
            record=accessible_project(db,project_id,current['id'])
            if database_snapshots and record['snapshot']:
                archive=db.execute('SELECT data FROM project_snapshots WHERE name=?',(record['snapshot'],)).fetchone()
                if archive is not None:
                    return Response(content=bytes(archive['data']),media_type='application/zip',headers={'Content-Disposition':'attachment; filename=backalor-project.zip','ETag':str(record['version'])})
        if not record['snapshot'] or not (snapshots/record['snapshot']).is_file():raise HTTPException(404,'Project has no snapshot')
        return FileResponse(snapshots/record['snapshot'],media_type='application/zip',filename='backalor-project.zip',headers={'ETag':str(record['version'])})

    @app.delete('/projects/{project_id}',status_code=204)
    def delete_project(project_id:str,current=Depends(user)):
        with database.connect() as db:
            db.execute('BEGIN IMMEDIATE');record=owned_project(db,project_id,current['id'])
            if record['snapshot']:db.execute('DELETE FROM project_snapshots WHERE name=?',(record['snapshot'],))
            db.execute('DELETE FROM projects WHERE id=? AND owner_id=?',(project_id,current['id']))
        if record['snapshot']:(snapshots/record['snapshot']).unlink(missing_ok=True)
        return Response(status_code=204)

    return app
