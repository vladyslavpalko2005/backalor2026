from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from app.client_config import configured_api_url
from app.backend_runtime import BackendRuntime


class CloudClientTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_environment_wins_without_reading_backend_secrets(self):
        (self.root/'.env').write_text('GOOGLE_CLIENT_SECRET=private\nBACKALOR_API_URL=https://file.example.org\n')
        self.assertEqual(configured_api_url(self.root,{'BACKALOR_API_URL':'https://env.example.org/'}),'https://env.example.org')
    def test_dotenv_reads_only_the_public_origin(self):
        for text in ['BACKALOR_API_URL="https://api.example.org" # cloud','export BACKALOR_API_URL=\'https://api.example.org\'','BACKALOR_API_URL=https://api.example.org']:
            (self.root/'.env').write_text(text+'\nGOOGLE_CLIENT_SECRET=hidden\n')
            self.assertEqual(configured_api_url(self.root,{}),'https://api.example.org')
    def test_bad_origin_is_rejected(self):
        for value in ('http://remote.example.org','https://u:p@example.org','https://example.org/path'):
            with self.assertRaises(ValueError):configured_api_url(self.root,{'BACKALOR_API_URL':value})
    def test_cloud_client_needs_no_backend_environment_or_local_data(self):
        runtime=BackendRuntime(self.root,environment={'BACKALOR_API_URL':'https://api.example.org'})
        with patch.object(runtime,'_probe',return_value={'service':'backalor','status':'ok','google_configured':True}),patch('app.backend_runtime.subprocess.Popen') as spawn:
            result=runtime.ensure_running()
            self.assertEqual(result['base_url'],'https://api.example.org');spawn.assert_not_called()
        self.assertFalse((self.root/'backend_data').exists());self.assertIsNone(runtime.process)
    def test_unreachable_cloud_never_creates_a_local_server(self):
        runtime=BackendRuntime(self.root,environment={'BACKALOR_API_URL':'https://api.example.org'})
        with patch.object(runtime,'_probe',return_value=None),patch('app.backend_runtime.subprocess.Popen') as spawn:
            with self.assertRaises(RuntimeError):runtime.ensure_running()
            spawn.assert_not_called()
        self.assertFalse((self.root/'backend_data').exists())

    def test_normal_startup_without_cloud_origin_never_falls_back_to_sqlite(self):
        runtime=BackendRuntime(self.root,environment={'BACKALOR_API_URL':''},allow_local=False)
        with patch('app.backend_runtime.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError,'BACKALOR_API_URL'):runtime.ensure_running()
            spawn.assert_not_called()
        self.assertFalse((self.root/'backend_data').exists())
