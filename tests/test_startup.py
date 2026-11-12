from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from radio_metadata.config import Config, ConfigStore
from radio_metadata.credentials import MemoryCredentials, CredentialError
from radio_metadata.startup import StartupError, startup_command, startup_name, commit_startup_settings


class MemoryStartup:
    def __init__(self, value=None):
        self.value = value
        self.writes = []

    def snapshot(self):
        return self.value

    def write(self, value):
        self.writes.append(value)
        self.value = value


class StartupTests(unittest.TestCase):
    def test_pythonw_and_frozen_commands_quote_paths_and_keep_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'Application with spaces'
            root.mkdir()
            python = root / 'python.exe';python.touch()
            pythonw = root / 'pythonw.exe';pythonw.touch()
            data = Path(tmp) / 'Profile with spaces'
            command = startup_command(data, True, executable=python, frozen=False)
            self.assertIn('"' + str(pythonw.resolve()) + '"', command)
            self.assertIn('-m radio_metadata', command)
            self.assertIn('"' + str(data.resolve()) + '"', command)
            self.assertTrue(command.endswith('--hidden'))
            exe = root / 'MetaDATA.exe';exe.touch()
            frozen = startup_command(data, executable=exe, frozen=True)
            self.assertIn('"' + str(exe.resolve()) + '"', frozen)
            self.assertNotIn('pythonw', frozen)
            self.assertNotIn('-m radio_metadata', frozen)
            self.assertNotIn('--hidden', frozen)
            self.assertEqual(startup_name(data), startup_name(data / '..' / data.name))
            self.assertNotEqual(startup_name(data), startup_name(data / 'other'))

    def test_missing_pythonw_and_long_run_values_fail_before_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            python = Path(tmp) / 'python.exe';python.touch()
            with self.assertRaises(StartupError):
                startup_command(Path(tmp), executable=python, frozen=False)
            with self.assertRaises(StartupError):
                startup_command(Path(tmp) / ('x' * 270), executable=python, frozen=True)

    def test_enable_disable_and_rollback_preserve_other_persistent_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp))
            original = store.load()
            vault = MemoryCredentials()
            backend = MemoryStartup()
            enabled = replace(original, start_with_windows=True, start_hidden=True)
            with patch('radio_metadata.startup.startup_command', return_value='"C:\\App\\MetaDATA.exe" --hidden'):
                commit_startup_settings(store, enabled, vault, {'token': 'test-key'}, original, backend=backend)
            self.assertEqual(backend.value, ('"C:\\App\\MetaDATA.exe" --hidden', 1))
            self.assertTrue(store.load().start_with_windows)
            self.assertEqual(vault.get('token'), 'test-key')
            self.assertNotIn('test-key', store.path.read_text())
            disabled = replace(enabled, start_with_windows=False)
            commit_startup_settings(store, disabled, vault, {}, enabled, backend=backend)
            self.assertIsNone(backend.value)
            self.assertFalse(store.load().start_with_windows)
            # Preserve the precise old registry type/value if a config save fails.
            old = ('previous command', 2)
            backend.value = old
            with patch('radio_metadata.startup.startup_command', return_value='new command'), \
                 patch.object(store, 'save', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    commit_startup_settings(store, enabled, vault, {'token': 'new-test-key'}, disabled, backend=backend)
            self.assertEqual(backend.value, old)
            self.assertEqual(vault.get('token'), 'test-key')
            self.assertFalse(store.load().start_with_windows)

    def test_demo_and_default_never_write_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp));original = store.load()
            backend = MemoryStartup(('do not touch', 1))
            commit_startup_settings(store, original, MemoryCredentials(), {}, original, backend=backend)
            self.assertEqual(backend.writes, [])
            demo = replace(original, start_with_windows=True)
            with patch('radio_metadata.startup.startup_command', side_effect=AssertionError('No OS command in demo')):
                commit_startup_settings(store, demo, MemoryCredentials(), {}, original, demo=True, backend=backend)
            self.assertEqual(backend.writes, [])

    def test_registration_denied_does_not_store_config_or_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp));original = store.load()
            backend = MemoryStartup()
            vault = MemoryCredentials()
            with patch('radio_metadata.startup.startup_command', return_value='command'), \
                 patch.object(backend, 'write', side_effect=PermissionError()):
                with self.assertRaises(StartupError):
                    commit_startup_settings(store, replace(original, start_with_windows=True), vault,
                                            {'token': 'not-saved'}, original, backend=backend)
            self.assertFalse(store.load().start_with_windows)
            self.assertEqual(vault.get('token'), '')

    def test_registry_adapter_only_changes_current_user_own_profile_entry(self):
        from contextlib import contextmanager
        from types import SimpleNamespace
        from radio_metadata.startup import WindowsStartup, RUN_KEY
        values = {'OtherApplication': ('keep this', 1)}
        calls = []
        @contextmanager
        def open_key(root, path, reserved, access):
            calls.append((root, path, access))
            yield 'key'
        def query(key, name):
            if name not in values:
                raise FileNotFoundError()
            return values[name]
        def write(key, name, reserved, value_type, value):
            values[name] = value, value_type
        def delete(key, name):
            if name not in values:
                raise FileNotFoundError()
            del values[name]
        fake = SimpleNamespace(HKEY_CURRENT_USER='current-user', KEY_READ=1, KEY_SET_VALUE=2,
                               OpenKey=open_key, CreateKeyEx=open_key, QueryValueEx=query,
                               SetValueEx=write, DeleteValue=delete)
        with tempfile.TemporaryDirectory() as tmp, patch.dict('sys.modules', winreg=fake), \
             patch('radio_metadata.startup.sys.platform', 'win32'):
            backend = WindowsStartup(Path(tmp))
            self.assertIsNone(backend.snapshot())
            backend.write(('application --hidden', 1))
            self.assertEqual(backend.snapshot(), ('application --hidden', 1))
            backend.write(None)
            self.assertEqual(values, {'OtherApplication': ('keep this', 1)})
            self.assertTrue(all(root == 'current-user' and path == RUN_KEY for root, path, _ in calls))
