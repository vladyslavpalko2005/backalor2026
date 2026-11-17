from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    public_url: str = 'http://127.0.0.1:8000'
    google_client_id: str = ''
    google_client_secret: str = ''
    session_seconds: int = 86400 * 7
    max_upload_bytes: int = 512 * 1024 * 1024
    database_url: str = ''
    require_postgres: bool = False
    snapshot_storage: str = 'filesystem'

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parent.parent/'.env', override=False)
        result = cls(Path(os.getenv('BACKALOR_DATA_DIR','backend_data')).resolve(),
                     (os.getenv('BACKALOR_PUBLIC_URL') or os.getenv('RENDER_EXTERNAL_URL') or 'http://127.0.0.1:8000').rstrip('/'),
                     os.getenv('GOOGLE_CLIENT_ID',''),os.getenv('GOOGLE_CLIENT_SECRET',''),
                     database_url=os.getenv('BACKALOR_DATABASE_URL',''),
                     require_postgres=os.getenv('BACKALOR_REQUIRE_POSTGRES','0')=='1',
                     snapshot_storage=os.getenv('BACKALOR_SNAPSHOT_STORAGE','filesystem'),
                     max_upload_bytes=int(os.getenv('BACKALOR_MAX_UPLOAD_BYTES',str(512*1024*1024))))
        url = urlsplit(result.public_url)
        if url.scheme not in ('https','http') or not url.netloc or url.query or url.fragment or url.username or url.password or url.path:
            raise ValueError('BACKALOR_PUBLIC_URL must be an origin without a path or credentials')
        if url.scheme == 'http' and url.hostname not in ('127.0.0.1','localhost','::1'):
            raise ValueError('Use HTTPS for a remotely accessible backend')
        if result.require_postgres and not result.database_url:
            raise ValueError('Cloud mode requires BACKALOR_DATABASE_URL; local SQLite is disabled')
        if result.database_url and not result.database_url.startswith(('postgresql://','postgres://')):
            raise ValueError('BACKALOR_DATABASE_URL must be a PostgreSQL URL')
        if result.snapshot_storage not in ('filesystem','database'):
            raise ValueError('BACKALOR_SNAPSHOT_STORAGE must be filesystem or database')
        if not 1<=result.max_upload_bytes<=512*1024*1024:
            raise ValueError('BACKALOR_MAX_UPLOAD_BYTES must be 1–536870912')
        if result.snapshot_storage=='database' and result.max_upload_bytes>20*1024*1024:
            raise ValueError('Database snapshot mode requires an upload limit of at most 20 MiB')
        return result

    @property
    def redirect_uri(self):
        return self.public_url+'/auth/google/callback'
