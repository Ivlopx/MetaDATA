"""Per-user Windows credentials. No plaintext fallback and no secrets in config.json."""
from hashlib import sha256
import os
from pathlib import Path
import threading


class CredentialError(RuntimeError):
    pass


def secret_id(service, *identity):
    identity = '\0'.join(str(part) for part in identity)
    return service + ':' + sha256(identity.encode('utf-8')).hexdigest()[:24]


class MemoryCredentials:
    """Explicitly transient backend for demonstration and tests only."""
    persistent = False

    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key, '')

    def set(self, key, value):
        if value:
            self.values[key] = value
        else:
            self.values.pop(key, None)


class WindowsCredentials:
    persistent = True

    def __init__(self, directory: Path, backend=None):
        self.namespace = 'MetaDATA/' + sha256(str(directory.resolve()).casefold().encode('utf-8')).hexdigest()[:24]
        self._backend = backend
        self._lock = threading.RLock()

    def backend(self):
        if self._backend is None:
            if os.name != 'nt':
                raise CredentialError('El guardado seguro de claves está disponible en Windows.')
            try:
                # Deliberately select the OS vault, never a third-party plaintext backend.
                from keyring.backends.Windows import WinVaultKeyring
                self._backend = WinVaultKeyring()
                self._backend.persist = 'local machine'
            except Exception:
                raise CredentialError('No se pudo abrir el almacén de credenciales de Windows. Reinstala los componentes de la app.') from None
        return self._backend

    def get(self, key):
        with self._lock:
            try:
                return self.backend().get_password(self.namespace, key) or ''
            except CredentialError:
                raise
            except Exception:
                raise CredentialError('Windows no permitió leer la clave guardada.') from None

    def set(self, key, value):
        with self._lock:
            try:
                backend = self.backend()
                if value:
                    backend.set_password(self.namespace, key, value)
                elif backend.get_password(self.namespace, key) is not None:
                    backend.delete_password(self.namespace, key)
            except CredentialError:
                raise
            except Exception:
                raise CredentialError('Windows no permitió guardar o eliminar la clave.') from None


def read_secret(credentials, key, legacy_env='', *, managed=False):
    try:
        value = credentials.get(key) if credentials else ''
    except CredentialError:
        # Keep existing installations working; UI never requires environment variables.
        value = ''
        if managed or not os.environ.get(legacy_env, ''):
            raise
    return value if managed else (value or os.environ.get(legacy_env, ''))


def commit_settings(store, config, credentials, changes):
    """Compensate vault writes if any write or atomic config save fails."""
    originals = {key: credentials.get(key) for key in changes}
    applied = []
    try:
        for key, value in changes.items():
            applied.append(key)
            credentials.set(key, value)
        store.save(config)
    except Exception:
        rollback_failed = False
        for key in reversed(applied):
            try:
                credentials.set(key, originals[key])
            except Exception:
                rollback_failed = True
        if rollback_failed:
            raise CredentialError('No se completó el guardado. Revisa las claves de las conexiones antes de continuar.') from None
        raise
