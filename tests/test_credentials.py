import asyncio
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from radio_metadata.config import Config, ConfigStore
from radio_metadata.credentials import (CredentialError, MemoryCredentials, WindowsCredentials,
    secret_id, read_secret, commit_settings)
from radio_metadata.connection_tests import check_connection, OverlayCredentials
from radio_metadata.outputs import LocalOutput, IcecastOutput, AzuraCastOutput, WebDavOutput
from radio_metadata.model import Snapshot, resolve
from radio_metadata.sources import RadioBossSource


class FakeVault:
    def __init__(self):
        self.items = {}
    def get_password(self, service, username):
        return self.items.get((service, username))
    def set_password(self, service, username, password):
        self.items[service, username] = password
    def delete_password(self, service, username):
        self.items.pop((service, username), None)


class CredentialsTests(unittest.TestCase):
    def test_vault_survives_new_instance_and_is_scoped_to_data_folder_and_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FakeVault()
            first = WindowsCredentials(Path(tmp), backend)
            key = secret_id('radioboss', 'http://localhost:9001/', 'dj')
            first.set(key, 'private')
            self.assertEqual(WindowsCredentials(Path(tmp), backend).get(key), 'private')
            self.assertEqual(WindowsCredentials(Path(tmp) / 'other', backend).get(key), '')
            self.assertEqual(first.get(secret_id('radioboss', 'http://other:9001/', 'dj')), '')
            first.set(key, '')
            self.assertEqual(first.get(key), '')

    def test_backend_errors_never_expose_credentials(self):
        class Broken(FakeVault):
            def set_password(self, *args):
                raise RuntimeError('private-secret')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CredentialError) as raised:
                WindowsCredentials(Path(tmp), Broken()).set('key', 'private-secret')
            self.assertNotIn('private-secret', str(raised.exception))

    def test_gui_values_override_legacy_and_deleted_values_stay_deleted(self):
        vault = MemoryCredentials()
        with patch.dict(os.environ, LEGACY_KEY='old'):
            self.assertEqual(read_secret(vault, 'key', 'LEGACY_KEY'), 'old')
            vault.set('key', 'new')
            self.assertEqual(read_secret(vault, 'key', 'LEGACY_KEY'), 'new')
            vault.set('key', '')
            self.assertEqual(read_secret(vault, 'key', 'LEGACY_KEY', managed=True), '')

    def test_atomic_config_failure_rolls_back_vault_changes(self):
        class BrokenStore:
            def save(self, config):
                raise OSError('read only')
        vault = MemoryCredentials()
        vault.set('first', 'old')
        with self.assertRaises(OSError):
            commit_settings(BrokenStore(), Config(), vault, {'first': 'new', 'second': 'new2'})
        self.assertEqual(vault.values, {'first': 'old'})

    def test_partial_vault_failure_rolls_back_all_affected_keys(self):
        class Broken(MemoryCredentials):
            def set(self, key, value):
                super().set(key, value)
                if value == 'fail':
                    raise CredentialError('Cannot write')
        vault = Broken()
        vault.set('first', 'old')
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(CredentialError):
            commit_settings(ConfigStore(Path(tmp)), Config(), vault, {'first': 'new', 'second': 'fail'})
        self.assertEqual(vault.values, {'first': 'old'})

    def test_v2_migration_preserves_settings_and_uses_native_theme(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp))
            old = asdict(Config(station_name='Estación de prueba', priority='spotify'))
            old['version'] = 2
            for field in ('theme', 'managed_credentials'):
                old.pop(field)
            raw = json.dumps(old).encode()
            store.path.write_bytes(raw)
            config = store.load()
            self.assertEqual(config.station_name, 'Estación de prueba')
            self.assertEqual(config.priority, 'spotify')
            self.assertEqual(config.theme, 'system')
            self.assertEqual((Path(tmp) / 'config.v2.backup.json').read_bytes(), raw)
            self.assertEqual(store.load(), config)

    def test_radioboss_reads_saved_password_without_environment(self):
        vault = MemoryCredentials()
        config = Config()
        key = secret_id('radioboss', config.radioboss_url, config.radioboss_user)
        vault.set(key, 'saved-password')
        real = httpx.AsyncClient
        seen = []
        def handler(request):
            seen.append(request.url.params['pass'])
            return httpx.Response(200, text='<root/>')
        with patch('radio_metadata.sources.httpx.AsyncClient', side_effect=lambda **kw: real(transport=httpx.MockTransport(handler), **kw)):
            asyncio.run(RadioBossSource(config, vault)._request(action='playbackinfo'))
        self.assertEqual(seen, ['saved-password'])

    def test_outputs_read_saved_keys_and_clear_song_fields_during_breaks(self):
        vault = MemoryCredentials()
        config = Config(azuracast_url='https://az.example')
        vault.set(secret_id('azuracast', config.azuracast_url), 'saved-api-key')
        target = {'url': 'https://ice.example', 'mount': '/live', 'username': 'source', 'managed_password': True, 'send_artwork_url': True}
        vault.set(secret_id('icecast', target['url'], target['mount'], 'source'), 'saved-password')
        received = []
        real = httpx.Client
        def handler(request):
            received.append(request)
            if request.method == 'POST':
                return httpx.Response(200, json={'success': True})
            return httpx.Response(200, text='<iceresponse><return>1</return><message>Metadata update successful</message></iceresponse>')
        with patch('radio_metadata.outputs.httpx.Client', side_effect=lambda **kw: real(transport=httpx.MockTransport(handler), **kw)):
            AzuraCastOutput(config, vault).publish(resolve([], config))
            IcecastOutput(target, vault).publish(resolve([], config), {'artwork_url': 'https://cdn.example/logo.png'})
        self.assertEqual(received[0].headers['X-API-Key'], 'saved-api-key')
        self.assertEqual(received[0].content, b'artist=&title=')
        self.assertEqual(received[1].url.params['song'], '')
        self.assertEqual(received[1].url.params['url'], '')
        self.assertIn('Basic ', received[1].headers['Authorization'])

    def test_logo_and_message_are_never_exported_as_a_song(self):
        from defusedxml import ElementTree as ET
        with tempfile.TemporaryDirectory() as tmp:
            logo = Path(tmp) / 'logo.png'
            logo.write_bytes(b'\x89PNG\r\n\x1a\nlogo')
            config = Config(logo_path=str(logo), station_name='Estación de prueba')
            output = LocalOutput(Path(tmp))
            for decision in (resolve([], config), resolve([Snapshot('radioboss', True, 'Campaña', 'Anuncio', r'C:\Ads\spot.mp3')], config)):
                state = output.publish(decision, config)
                self.assertEqual(state['artist'], '')
                self.assertEqual(state['title'], '')
                self.assertEqual(state['text'], '')
                self.assertEqual(state['artwork_file'], '')
                self.assertTrue(state['logo_file'])
                self.assertTrue(state['display_message'])
                self.assertFalse(state['is_music'])
                self.assertEqual((Path(tmp) / 'nowplaying.txt').read_text().strip(), '')
                self.assertEqual(ET.fromstring((Path(tmp) / 'nowplaying.xml').read_bytes()).find('TRACK').get('TITLE'), '')
                self.assertEqual(ET.fromstring((Path(tmp) / 'nowplaying.xml').read_bytes()).find('TRACK').get('CASTTITLE'), '')

    def test_real_song_without_artwork_uses_logo_but_keeps_real_song_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            logo = Path(tmp) / 'logo.png'
            logo.write_bytes(b'\x89PNG\r\n\x1a\nlogo')
            config = Config(logo_path=str(logo), spotify_publish=True)
            track = Snapshot('spotify', True, 'Artista real', 'Canción real', kind='music')
            state = LocalOutput(Path(tmp)).publish(resolve([track], config), config)
            self.assertTrue(state['is_music'])
            self.assertEqual(state['artwork_file'], state['logo_file'])
            self.assertEqual(state['artwork_origin'], 'station_logo')
            self.assertEqual(state['artist'], 'Artista real')
            self.assertEqual(state['title'], 'Canción real')
            self.assertEqual(state['display_message'], '')
            from defusedxml import ElementTree as ET
            self.assertEqual(ET.fromstring((Path(tmp) / 'nowplaying.xml').read_bytes()).find('TRACK').get('CASTTITLE'), 'Artista real - Canción real')

    def test_readonly_connection_checks_use_pending_keys_without_publishing(self):
        vault = MemoryCredentials()
        config = Config(azuracast_url='https://az.example', azuracast_write_enabled=True,
                        webdav_upload_url='https://dav.example/folder', webdav_username='dj')
        key = secret_id('azuracast', config.azuracast_url)
        dav_key = secret_id('webdav', config.webdav_upload_url, 'dj')
        overlay = OverlayCredentials(vault, {key: 'unsaved-api', dav_key: 'unsaved-password'})
        methods = []
        real = httpx.Client
        def handler(request):
            methods.append(request.method)
            if request.method == 'GET':
                self.assertEqual(request.headers['X-API-Key'], 'unsaved-api')
                return httpx.Response(200, json={'id': 2})
            return httpx.Response(207, text='<multistatus/>')
        with patch('radio_metadata.connection_tests.httpx.Client', side_effect=lambda **kw: real(transport=httpx.MockTransport(handler), **kw)):
            self.assertTrue(asyncio.run(check_connection('AzuraCast', config, overlay, Path('.')))[0])
            self.assertTrue(asyncio.run(check_connection('Alojamiento de carátulas', config, overlay, Path('.')))[0])
        self.assertEqual(methods, ['GET', 'PROPFIND'])
        self.assertEqual(vault.values, {})
