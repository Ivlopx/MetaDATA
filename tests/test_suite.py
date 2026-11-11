import asyncio
import base64
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from radio_metadata.config import Config
from radio_metadata.credentials import MemoryCredentials
from radio_metadata.model import Snapshot, Decision, resolve, folder_allowed
from radio_metadata.source_catalog import windows_source_id
from radio_metadata.sources import WindowsMediaSource, discover_windows_sessions
from radio_metadata.receiver import ReceiverServer, ReceiverStore
from radio_metadata.publication import ReceiverOutput, publication_key

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==')


def source(app='vlc.exe', **changes):
    return dict(id=windows_source_id(app), app_id=app, name='VLC', enabled=True,
                publish=True, allow_unknown=False, **changes)


class SourceRulesTests(unittest.TestCase):
    def test_folder_nonrecursive_and_blacklist_precedence(self):
        config = Config(folder_rules=[dict(path=r'C:\Music', action='allow', recursive=False)])
        self.assertTrue(folder_allowed(r'c:\music\song.mp3', config))
        self.assertFalse(folder_allowed(r'C:\Music\Album\song.mp3', config))
        config.folder_rules[0]['recursive'] = True
        config.folder_rules.append(dict(path=r'C:\Music\Ads', action='block', recursive=True))
        self.assertTrue(folder_allowed(r'C:\Music\Album\song.mp3', config))
        self.assertFalse(folder_allowed(r'C:\Music\Ads\Sub\song.mp3', config))
        self.assertFalse(folder_allowed(r'C:\MusicOther\song.mp3', config))

    def test_legacy_rules_and_no_whitelist_fail_closed(self):
        config = Config(music_folders=[r'C:\Music'], excluded_folders=[r'C:\Music\Ads'])
        self.assertTrue(folder_allowed(r'C:\Music\Album\song.mp3', config))
        self.assertFalse(folder_allowed(r'C:\Music\Ads\song.mp3', config))
        self.assertFalse(folder_allowed(r'C:\Music\song.mp3', Config()))

    def test_extra_source_priority_does_not_leak_lower_song_during_ad(self):
        row = source()
        config = Config(windows_sources=[row], source_priority=[row['id'], 'spotify'], spotify_publish=True)
        config.validate()
        extra = Snapshot(row['id'], True, 'Artist', 'Track', kind='music')
        spotify = Snapshot('spotify', True, 'Other', 'Other track', kind='music')
        self.assertEqual(resolve([spotify, extra], config).song, extra)
        self.assertIsNone(resolve([spotify, replace(extra, title='Publicidad')], config).song)
        self.assertEqual(resolve([spotify, extra], config, 'spotify').song, spotify)
        self.assertIsNone(resolve([spotify, replace(extra, kind='unknown')], config).song)
        row['allow_unknown'] = True
        self.assertIsNotNone(resolve([replace(extra, kind='unknown')], config).song)
        self.assertIsNone(resolve([replace(extra, kind='non_music')], config).song)
        row['publish'] = False
        self.assertIsNone(resolve([extra], config).song)

    def test_invalid_source_ids_and_rules_are_rejected(self):
        for config in (Config(windows_sources=[dict(source(), id='invalid')]),
                       Config(folder_rules=[dict(path='x', action='allow', recursive='yes')]),
                       Config(source_priority=['missing']),
                       Config(receiver_enabled=True, receiver_url='http://receiver.example'),
                       Config(receiver_enabled=True, receiver_url='https://receiver.example', poll_seconds=30)):
            with self.assertRaises(ValueError):
                config.validate()


class WindowsSessionTests(unittest.IsolatedAsyncioTestCase):
    def session(self, app='vlc.exe', status=1, kind=1):
        media = NS(artist='Artist', title='Title', album_title='Album', album_artist='Artist',
                   genres=['Pop'], track_number=2, thumbnail=None, playback_type=kind)
        return NS(source_app_user_model_id=app, get_playback_info=lambda: NS(playback_status=status),
                  try_get_media_properties_async=AsyncMock(return_value=media))

    async def poll(self, sessions):
        with patch('radio_metadata.sources.sys.platform', 'win32'), \
             patch('radio_metadata.sources.windows_sessions', AsyncMock(return_value=sessions)), \
             patch('radio_metadata.sources.windows_media_types', return_value=(NS(PLAYING=1), NS(MUSIC=1, UNKNOWN=0))):
            return await WindowsMediaSource('test', 'vlc.exe').poll()

    async def test_exact_identity_and_real_metadata(self):
        result = await self.poll([self.session('fake-vlc.exe'), self.session()])
        self.assertEqual((result.artist, result.title, result.album), ('Artist', 'Title', 'Album'))
        self.assertTrue(result.playing)
        self.assertEqual(result.kind, 'music')

    async def test_paused_missing_and_multiple_sessions(self):
        self.assertTrue((await self.poll([self.session(status=0)])).available)
        self.assertFalse((await self.poll([])).available)
        self.assertTrue((await self.poll([self.session(), self.session()])).error)

    async def test_changed_metadata_is_not_published(self):
        session = self.session()
        first = session.try_get_media_properties_async.return_value
        session.try_get_media_properties_async.side_effect = [first, NS(artist='Next', title='Next', album_title='Next', playback_type=1)]
        result = await self.poll([session])
        self.assertTrue(result.error)
        self.assertFalse(result.playing)
        self.assertEqual((await self.poll([self.session(kind=2)])).kind, 'non_music')

    async def test_discovery_groups_sessions_not_installed_inventory(self):
        with patch('radio_metadata.sources.windows_sessions', AsyncMock(return_value=[self.session(), self.session(status=0)])), \
             patch('radio_metadata.sources.windows_media_types', return_value=(NS(PLAYING=1), NS())):
            rows = await discover_windows_sessions()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['sessions'], 2)
        self.assertTrue(rows[0]['playing'])


class ReceiverTests(unittest.TestCase):
    def test_store_clear_expiry_restart_and_single_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReceiverStore(tmp, 15)
            payload = dict(state=dict(is_music=True, artist='Artist', title='Title', album='Album', filename='private'),
                           artwork_base64=base64.b64encode(PNG).decode())
            revision = store.put(payload)
            state, image = ReceiverStore(tmp, 15).snapshot()
            self.assertEqual(image, PNG)
            self.assertNotIn('filename', state)
            self.assertFalse(store.heartbeat('old-revision'))
            self.assertTrue(store.heartbeat(revision))
            with patch('radio_metadata.receiver.time.time', return_value=time.time() + 16):
                state, image = store.snapshot()
            self.assertTrue(state['expired'])
            self.assertFalse(state['is_music'])
            self.assertEqual((state['artist'], state['artwork_url'], image), ('', '', b''))
            payload['state']['is_music'] = False
            store.put(payload)
            state, image = store.snapshot()
            self.assertEqual((state['title'], state['album'], image), ('', '', b''))
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ['current.json'])

    def test_http_publisher_auth_atomic_cover_heartbeat_and_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            server = ReceiverServer(('127.0.0.1', 0), root / 'data', 'x' * 40, 15)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = 'http://127.0.0.1:' + str(server.server_port)
            config = Config(receiver_enabled=True, receiver_url=url)
            vault = MemoryCredentials()
            vault.set(publication_key(config), 'x' * 40)
            (root / 'covers').mkdir()
            (root / 'covers' / 'image.png').write_bytes(PNG)
            writer = ReceiverOutput(config, root, vault)
            state = dict(is_music=True, artist='Artist', title='Song', album='Album', artwork_file='covers/image.png')
            try:
                with httpx.Client(trust_env=False) as client:
                    self.assertEqual(client.put(url + '/api/v1/nowplaying', json={}).status_code, 401)
                    self.assertEqual(client.get(url + '/api/v1/check', headers={'Authorization': 'Bearer ' + 'x'*40}).status_code, 200)
                    self.assertEqual(client.get(url + '/../../config.json').status_code, 404)
                    self.assertIn('confirmada', writer.send(None, state))
                    public = client.get(url + '/nowplaying.json').json()
                    self.assertEqual(public['album'], 'Album')
                    self.assertEqual(client.get(url + public['artwork_url']).content, PNG)
                    self.assertEqual(client.get(url + '/artwork').content, PNG)
                    with patch.object(server.store, 'put', wraps=server.store.put) as put:
                        writer.next_attempt = 0
                        self.assertIn('confirmada', writer.send(None, state))
                        put.assert_not_called()
                    state['is_music'] = False
                    self.assertIn('vacíos confirmados', writer.send(None, state))
                    public = client.get(url + '/nowplaying.json').json()
                    self.assertEqual(public['artist'], '')
                    self.assertEqual(client.get(url + '/artwork').status_code, 204)
                    self.assertEqual(client.get(url + '/artwork/old').status_code, 404)
                    self.assertEqual(client.put(url + '/api/v1/nowplaying', headers={
                        'Authorization': 'Bearer ' + 'x'*40}, json={'state': {'is_music': True}}).status_code, 400)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_retry_sends_latest_state_instead_of_queued_song(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Config(receiver_url='http://127.0.0.1:9999')
            writer = ReceiverOutput(config, Path(tmp), MemoryCredentials())
            self.assertTrue(writer.send(None, dict(is_music=True, artist='Old', title='Old')).startswith('Error'))
            writer.next_attempt = 0
            vault = writer.credentials
            vault.set(publication_key(config), 'x'*40)
            response = httpx.Response(200, json={'ok': True, 'revision': 'next'}, request=httpx.Request('PUT', config.receiver_url))
            with patch('radio_metadata.publication.httpx.Client') as client:
                send = client.return_value.__enter__.return_value.put
                send.return_value = response
                writer.send(None, dict(is_music=False))
                self.assertFalse(send.call_args.kwargs['json']['state']['is_music'])
                self.assertEqual(send.call_args.kwargs['json']['artwork_base64'], '')
