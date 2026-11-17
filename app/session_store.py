"""Remember one verified Google session per API origin using the OS credential vault.

The JSON file contains only a profile hint and origin, never a token. A missing
or locked system vault disables persistence without a plaintext fallback.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys
from .api_client import normalize_server_url
from .storage import atomic_write


class SessionStoreError(RuntimeError):
    pass


class SecureSessionStore:
    service='Backalor desktop session'
    def __init__(self,directory,backend=None):
        self.directory=Path(directory);self._backend=backend
    def _key(self,origin):return hashlib.sha256(normalize_server_url(origin).encode('utf-8')).hexdigest()
    def _path(self,origin):return self.directory/('session-'+self._key(origin)+'.json')
    def _vault(self):
        if self._backend is None:
            try:
                if sys.platform=='darwin':
                    from keyring.backends.macOS import Keyring
                elif sys.platform=='win32':
                    from keyring.backends.Windows import WinVaultKeyring as Keyring
                elif sys.platform.startswith('linux'):
                    from keyring.backends.SecretService import Keyring
                else:raise RuntimeError('Unsupported platform')
                backend=Keyring()
                if backend.priority<=0:raise RuntimeError('System vault unavailable')
                self._backend=backend
            except Exception:
                raise SessionStoreError('Системне сховище недоступне. Вхід працює, але сесію не буде збережено.') from None
        return self._backend
    def has_record(self,origin):
        try:
            data=json.loads(self._path(origin).read_text(encoding='utf-8'))
            return data.get('schema_version')==1 and data.get('origin')==normalize_server_url(origin) and isinstance(data.get('profile'),dict)
        except (OSError,ValueError,AttributeError):return False
    def save(self,origin,token,profile):
        origin=normalize_server_url(origin)
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',token):raise SessionStoreError('Invalid session token')
        if not isinstance(profile,dict) or any(not isinstance(profile.get(key),str) or len(profile[key])>1000 for key in ('id','name','email')):
            raise SessionStoreError('Invalid profile')
        try:self._vault().set_password(self.service,self._key(origin),token)
        except Exception:raise SessionStoreError('Не вдалося зберегти вхід у системному сховищі.') from None
        try:
            atomic_write(self._path(origin),json.dumps({'schema_version':1,'origin':origin,'profile':{key:profile[key] for key in ('id','name','email')}},ensure_ascii=False,indent=2).encode('utf-8'))
            self._path(origin).chmod(0o600)
        except OSError:raise SessionStoreError('Не вдалося зберегти налаштування повторного входу.') from None
    def load(self,origin):
        if not self.has_record(origin):return None
        try:token=self._vault().get_password(self.service,self._key(origin))
        except Exception:raise SessionStoreError('Не вдалося прочитати збережений вхід. Увійди через Google.') from None
        if not isinstance(token,str) or not token or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',token):
            self.forget(origin);return None
        return token
    def forget(self,origin):
        try:self._path(origin).unlink(missing_ok=True)
        except OSError:raise SessionStoreError('Не вдалося видалити налаштування збереженого входу.') from None
    def clear(self,origin):
        # Removing the hint first prevents restoration even if the vault is locked.
        existed=self.has_record(origin);self.forget(origin)
        if existed:
            try:self._vault().delete_password(self.service,self._key(origin))
            except Exception:raise SessionStoreError('Сесію відкликано; не вдалося очистити запис системного сховища.') from None
