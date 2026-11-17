from pathlib import Path
import importlib.util
import tempfile
import unittest
import zipfile


class CloudBundleTests(unittest.TestCase):
    def test_deployment_bundle_contains_server_sources_without_research_data_or_secrets(self):
        root=Path(__file__).resolve().parent.parent
        spec=importlib.util.spec_from_file_location('package_cloud',root/'scripts/package-cloud.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)/'cloud.zip';module.package(target)
            with zipfile.ZipFile(target) as archive:
                names=set(archive.namelist())
                self.assertIn('backend/main.py',names);self.assertIn('render.yaml',names);self.assertIn('Dockerfile',names)
                self.assertNotIn('.env',names)
                self.assertFalse(any(name.startswith(('app/','backend_data/','annotations/','images_raw/','.venv','reports/')) for name in names))
                self.assertFalse(any(name.endswith(('.sqlite3','.pt','.pyc')) for name in names))
                self.assertTrue(all(name.startswith(('backend/','deploy/')) or name in {'Dockerfile','.dockerignore','render.yaml','requirements-backend.txt','.env.cloud.example','CLOUD.md','FREE_HOSTING.md'} for name in names))
