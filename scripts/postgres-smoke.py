"""Run the complete API suite against a disposable real PostgreSQL server.

Test-only dependency: embedded-postgres. This never provisions a production DB.
Every create_app receives a separate schema; the temporary cluster is removed.
"""
from __future__ import annotations
import hashlib
import os
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode,quote
ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(ROOT),str(ROOT/'tests_backend')]


def main():
    import embedded_postgres
    import psycopg
    import test_api
    from backend.main import create_app
    with tempfile.TemporaryDirectory(prefix='backalor-pg-test-') as temporary:
        with embedded_postgres.get_server(Path(temporary)/'cluster') as postgres:
            origin=postgres.get_uri()
            schemas=set()
            def factory(settings=None):
                assert settings is not None,'Only isolated test settings are allowed'
                name='test_'+hashlib.sha256(str(settings.data_dir).encode()).hexdigest()[:24]
                if name not in schemas:
                    with psycopg.connect(origin,autocommit=True) as connection:
                        from psycopg import sql
                        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
                    schemas.add(name)
                url=urlsplit(origin);query=dict(parse_qsl(url.query));query['options']='-c search_path='+name
                database_url=urlunsplit((url.scheme,url.netloc,url.path,urlencode(query,quote_via=quote),url.fragment))
                cloud=replace(settings,database_url=database_url,require_postgres=True)
                if os.getenv('BACKALOR_TEST_DATABASE_SNAPSHOTS')=='1' and settings.snapshot_storage!='database':
                    cloud=replace(cloud,snapshot_storage='database',max_upload_bytes=min(cloud.max_upload_bytes,20*1024*1024))
                app=create_app(cloud)
                assert not (settings.data_dir/'backalor.sqlite3').exists()
                return app
            with patch.object(test_api,'create_app',side_effect=factory):
                suite=unittest.defaultTestLoader.discover(str(ROOT/'tests_backend'))
                result=unittest.TextTestRunner(verbosity=2).run(suite)
            print('POSTGRESQL_SCHEMAS',len(schemas))
            print('NO_SQLITE_IN_CLOUD_TEST_APPS',True)
            if not result.wasSuccessful():return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
