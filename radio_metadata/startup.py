"""Explicit per-user Windows logon registration, scoped to one data profile."""
from hashlib import sha256
from pathlib import Path
import subprocess
import sys

from .credentials import commit_settings

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


class StartupError(RuntimeError):
    pass


def startup_name(directory):
    digest = sha256(str(Path(directory).resolve()).casefold().encode()).hexdigest()[:12]
    return 'MetaDATA-' + digest


def startup_command(directory, hidden=False, *, executable=None, frozen=None):
    executable = Path(executable or sys.executable).resolve()
    frozen = getattr(sys, 'frozen', False) if frozen is None else frozen
    if frozen:
        args = [str(executable)]
    else:
        pythonw = executable.with_name('pythonw.exe')
        if not pythonw.is_file():
            raise StartupError('No se encontró pythonw.exe. Vuelve a ejecutar instalar.bat antes de activar el inicio con Windows.')
        args = [str(pythonw), '-m', 'radio_metadata']
    args += ['--data-dir', str(Path(directory).resolve())]
    if hidden:
        args.append('--hidden')
    command = subprocess.list2cmdline(args)
    # Microsoft documents a 260-character limit for Run values.
    if len(command.encode('utf-16-le')) // 2 > 260 or any(ord(c) < 32 for c in command):
        raise StartupError('La ruta de inicio es demasiado larga. Usa una carpeta de aplicación y datos con rutas más cortas.')
    return command


class WindowsStartup:
    def __init__(self, directory):
        if sys.platform != 'win32':
            raise StartupError('El inicio automático de sesión está disponible en Windows.')
        self.name = startup_name(directory)

    def snapshot(self):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                return winreg.QueryValueEx(key, self.name)
        except FileNotFoundError:
            return None

    def write(self, saved):
        import winreg
        if saved is None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, self.name)
            except FileNotFoundError:
                pass
        else:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, self.name, 0, saved[1], saved[0])


def commit_startup_settings(store, config, credentials, changes, original, *, demo=False, backend=None):
    """Restore the exact Run value if vault/config save fails. No demo OS writes."""
    active = config.start_with_windows or original.start_with_windows
    if demo or not active:
        return commit_settings(store, config, credentials, changes)
    if backend is None and sys.platform != 'win32':
        if config.start_with_windows != original.start_with_windows:
            raise StartupError('El inicio con Windows solo puede cambiarse desde Windows.')
        return commit_settings(store, config, credentials, changes)
    command = startup_command(store.directory, config.start_hidden) if config.start_with_windows else None
    backend = backend or WindowsStartup(store.directory)
    try:
        previous = backend.snapshot()
        backend.write((command, 1) if command else None)  # REG_SZ = 1
    except OSError:
        raise StartupError('Windows no permitió actualizar el inicio automático. No se guardaron los cambios.') from None
    try:
        commit_settings(store, config, credentials, changes)
    except Exception:
        try:
            backend.write(previous)
        except OSError:
            raise StartupError('No se completó el guardado ni la restauración del inicio automático. Revisa las aplicaciones de inicio en Windows.') from None
        raise
