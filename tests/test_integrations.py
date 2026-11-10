from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import asyncio
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import urlopen, Request

import httpx

from radio_metadata.config import Config, ConfigStore
from radio_metadata.engine import Engine
from radio_metadata.model import resolve
from radio_metadata.outputs import AzuraCastOutput, IcecastOutput, LocalOutput, WebDavOutput
from radio_metadata.remote import RemoteMonitor, azuracast_state, icecast_state
from radio_metadata.sources import RadioBossSource
from radio_metadata.storage import History
from radio_metadata.webserver import LocalServer, live_state
from test_core import music

PNG = b'\x89PNG\r\n\x1a\nfixture'


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(music_folders=[r'C:\Musica'])
        self.decision = resolve([music(album='Álbum & <vivo>', year='2026', genre='Pop', duration_ms=123000,
                                      artwork=PNG, artwork_origin='radioboss_tag')], self.config)
        self.real_client = httpx.Client

    def client(self, handler):
        return patch('httpx.Client', side_effect=lambda **kw: self.real_client(transport=httpx.MockTransport(handler), **kw))

    def test_migrates_v1_config_once_preserving_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp))
            original = {'version': 1, 'station_name': 'Mi radio personalizada', 'priority': 'spotify'}
            raw = json.dumps(original).encode()
            store.path.write_bytes(raw)
            loaded = store.load()
            self.assertEqual(loaded.version, 4)
            self.assertEqual(loaded.priority, 'spotify')
            self.assertFalse(loaded.webdav_enabled)
            self.assertFalse(loaded.azuracast_write_enabled)
            self.assertEqual((Path(tmp) / 'config.v1.backup.json').read_bytes(), raw)
            self.assertEqual(store.load(), loaded)

    def test_migrates_old_history_without_losing_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'history.db'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE songs(id INTEGER PRIMARY KEY,played_at TEXT,source TEXT,artist TEXT,title TEXT)')
                db.execute("INSERT INTO songs VALUES(1,'2026-01-01','radioboss','A','B')")
            history = History(path)
            history.record(self.decision)
            self.assertEqual(len(history.recent()), 2)
            self.assertEqual(history.recent()[0][4], 'Álbum & <vivo>')
            self.assertEqual(history.recent()[1][2:4], ('A', 'B'))
            history.close()

    def test_exports_music_then_break_without_leaking_rich_ad_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = LocalOutput(Path(tmp))
            state = output.publish(self.decision, self.config)
            self.assertEqual(state['album'], 'Álbum & <vivo>')
            self.assertNotIn('filename', state)
            from defusedxml import ElementTree as ET
            self.assertEqual(ET.fromstring((Path(tmp) / 'nowplaying.xml').read_bytes()).find('TRACK').get('ALBUM'), state['album'])
            ad = resolve([music(title='Anuncio', album='Nombre privado de campaña', artwork=PNG)], self.config)
            state = output.publish(ad, self.config)
            for suffix in ('json', 'xml', 'txt'):
                self.assertNotIn('campaña', (Path(tmp) / ('nowplaying.' + suffix)).read_text())
            self.assertFalse(state['is_music'])
            self.assertEqual(state['album'], '')
            self.assertEqual(state['artwork_file'], '')

    def test_stale_state_falls_back_to_logo_and_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            logo = Path(tmp) / 'logo.png'
            logo.write_bytes(PNG)
            config = replace(self.config, logo_path=str(logo))
            state = LocalOutput(Path(tmp)).publish(self.decision, config)
            future = datetime.fromisoformat(state['updated_at']) + timedelta(seconds=config.stale_seconds + 1)
            stale = live_state(Path(tmp), future)
            self.assertFalse(stale['is_music'])
            self.assertEqual(stale['artwork_file'], '')
            self.assertEqual(stale['text'], '')
            self.assertEqual(stale['album'], '')

    def test_kh_numeric_success_with_rejection_message_is_failure(self):
        target = {'url': 'https://ice.example', 'mount': '/live.mp3', 'password_env': 'DUMMY_ICE'}
        output = IcecastOutput(target)
        def handler(request):
            return httpx.Response(200, text='<iceresponse><return>1</return><message>Mountpoint will not accept this URL update</message></iceresponse>')
        with self.client(handler), patch.dict(os.environ, DUMMY_ICE='fake'):
            self.assertIn('Error', output.send(self.decision))
            self.assertEqual(output.failures, 1)

    def test_kh_readback_checks_mount_and_artwork_url(self):
        target = {'url': 'https://ice.example', 'mount': '/live.mp3', 'password_env': 'DUMMY_ICE',
                  'send_artwork_url': True, 'verify_url': 'https://ice.example/status-json.xsl'}
        output = IcecastOutput(target)
        def handler(request):
            if request.url.path == '/admin/metadata':
                self.assertEqual(request.url.params['url'], 'https://cdn.example/art.png')
                return httpx.Response(200, text='<iceresponse><return>1</return><message>Metadata update successful</message></iceresponse>')
            return httpx.Response(200, json={'icestats': {'source': [
                {'listenurl': 'https://ice.example/other.mp3', 'title': 'Other'},
                {'listenurl': 'https://ice.example/listen/on-air/live.mp3', 'title': self.decision.text,
                 'metadata_url': 'https://cdn.example/art.png'}]}})
        with self.client(handler), patch.dict(os.environ, DUMMY_ICE='fake'):
            self.assertIn('verificados', output.send(self.decision, {'artwork_url': 'https://cdn.example/art.png'}))
        def stale(request):
            if request.url.path == '/admin/metadata':
                return httpx.Response(200, text='<iceresponse><return>1</return><message>Metadata update successful</message></iceresponse>')
            return httpx.Response(200, json={'icestats': {'source': {'listenurl': 'https://ice.example/live.mp3', 'title': 'Old song'}}})
        with self.client(stale), patch.dict(os.environ, DUMMY_ICE='fake'):
            output.next_attempt = 0
            self.assertIn('Error', output.send(self.decision, {'artwork_url': 'https://cdn.example/art.png'}))

    def test_azuracast_sender_only_uses_supported_fields_and_clears_on_break(self):
        output = AzuraCastOutput(self.config)
        received = []
        def handler(request):
            self.assertTrue(request.url.path.endswith('/api/station/2/nowplaying/update'))
            self.assertEqual(request.headers['X-API-Key'], 'fake')
            from urllib.parse import parse_qs
            received.append(parse_qs(request.content.decode(), keep_blank_values=True))
            return httpx.Response(200, json={'success': True})
        with self.client(handler), patch.dict(os.environ, AZURACAST_API_KEY='fake'):
            output.send(self.decision)
            self.assertEqual(set(received[0]), {'artist', 'title'})
            output.send(resolve([], self.config))
            self.assertEqual(received[1]['artist'], [''])
            self.assertEqual(received[1]['title'], [''])

    def test_webdav_uploads_assets_before_json_and_does_not_leak_credentials(self):
        config = replace(self.config, webdav_upload_url='https://dav.example/folder', webdav_public_url='https://cdn.example/radio')
        with tempfile.TemporaryDirectory() as tmp:
            state = LocalOutput(Path(tmp)).publish(self.decision, config)
            output = WebDavOutput(config, Path(tmp))
            requests = []
            def handler(request):
                requests.append(request)
                self.assertIn(request.method, ('MKCOL', 'PUT'))
                return httpx.Response(201)
            with self.client(handler), patch.dict(os.environ, METADATA_WEBDAV_PASSWORD='fake'):
                output.send(self.decision, state)
            self.assertEqual(requests[0].method, 'MKCOL')
            self.assertTrue(requests[1].url.path.endswith('.png'))
            self.assertTrue(requests[-1].url.path.endswith('/nowplaying.json'))
            public = json.loads(requests[-1].content)
            self.assertEqual(public['album'], 'Álbum & <vivo>')
            self.assertTrue(output.artwork_url.startswith('https://cdn.example/radio/covers/artwork-'))
            self.assertNotIn('fake', requests[-1].content.decode())
            self.assertNotIn('filename', public)
            ad = resolve([], config)
            ad_state = LocalOutput(Path(tmp)).publish(ad, config)
            def fail(request):
                return httpx.Response(503)
            with self.client(fail), patch.dict(os.environ, METADATA_WEBDAV_PASSWORD='fake'):
                self.assertIn('Error', output.send(ad, ad_state))
                self.assertEqual(output.artwork_url, '')

    def test_monitor_never_publishes_and_tracks_offline_and_mismatch(self):
        seen = []
        def handler(request):
            seen.append(request.method)
            if '/api/nowplaying/' in request.url.path:
                return httpx.Response(200, json={'is_online': True, 'now_playing': {'song': {'text': self.decision.text, 'album': 'Remote album', 'art': 'https://cover.example/a.png'}}})
            return httpx.Response(200, json={'icestats': {'source': {'listenurl': 'https://orofm.live/listen/on-air/vocesdetepezala/orofm/stream.mp3', 'title': 'Other title'}}})
        with self.client(handler):
            monitor = RemoteMonitor(self.config)
            records = monitor.poll(self.decision.text)
            self.assertTrue(records[0]['matches'])
            self.assertFalse(records[1]['matches'])
            self.assertTrue(records[1]['online'])
            self.assertEqual(monitor.poll('New song')[0]['matches'], False)
            self.assertEqual(len(seen), 2)
        self.assertEqual(set(seen), {'GET'})

    def test_monitor_failure_does_not_reuse_old_success(self):
        monitor = RemoteMonitor(self.config)
        monitor.records = [{'service': 'AzuraCast', 'online': True, 'error': '', 'text': self.decision.text}]
        def handler(request):
            return httpx.Response(503)
        with self.client(handler):
            records = monitor.poll(self.decision.text, force=True)
            self.assertFalse(records[0]['matches'])
            self.assertTrue(records[0]['error'])
            self.assertEqual(records[0]['text'], '')

    def test_radioboss_enriches_album_and_duration_from_tags(self):
        source = RadioBossSource(self.config)
        from test_core import xml
        tags = b'<TagInfo><File Album="Album" Year="2020" Genre="Rock" Duration="200000" TypeIdentifier="Music"/></TagInfo>'
        with patch.object(source, '_request', side_effect=[xml(), tags, xml()]):
            track = asyncio.run(source.poll())
            self.assertEqual((track.album, track.year, track.duration_ms), ('Album', '2020', 200000))

    def test_demo_blocks_all_remote_outputs_even_when_enabled(self):
        config = replace(self.config, remote_monitor_enabled=True, azuracast_write_enabled=True,
                         webdav_enabled=True, webdav_upload_url='https://dav.example/folder', webdav_public_url='https://cdn.example/radio')
        with tempfile.TemporaryDirectory() as tmp:
            engine = Engine(config, Path(tmp), demo=True)
            with patch('httpx.Client', side_effect=AssertionError('No remote requests')), patch('httpx.AsyncClient', side_effect=AssertionError('No remote requests')):
                decision, *_ = asyncio.run(engine.tick())
                self.assertIsNotNone(decision.song)
                self.assertEqual(engine.outputs, [])
                self.assertIsNone(engine.webdav)
                self.assertIsNone(engine.monitor)
            engine.close()

    def test_real_engine_ignores_retired_direct_destinations_in_old_profiles(self):
        from radio_metadata.credentials import MemoryCredentials
        for legacy in [dict(azuracast_write_enabled=True, remote_monitor_enabled=True),
                       dict(icecast_targets=[dict(url='https://radio.example', mount='/test', enabled=True)],
                            remote_monitor_enabled=True)]:
            config = Config(spotify_enabled=False, radioboss_enabled=False, **legacy)
            with tempfile.TemporaryDirectory() as tmp:
                with patch('httpx.Client', side_effect=AssertionError('Retired remote request')), \
                     patch('httpx.AsyncClient', side_effect=AssertionError('Retired remote request')):
                    engine = Engine(config, Path(tmp), credentials=MemoryCredentials())
                    try:
                        decision, snapshots, statuses, _ = asyncio.run(engine.tick())
                        self.assertIsNone(decision.song)
                        self.assertFalse(snapshots)
                        self.assertEqual(engine.outputs, [])
                        self.assertIsNone(engine.monitor)
                        self.assertTrue((Path(tmp) / 'output/nowplaying.json').exists())
                    finally:
                        engine.close()

    def test_rejects_insecure_or_ambiguous_publish_configuration(self):
        cases = [replace(self.config, webdav_enabled=True), replace(self.config, webdav_public_url='http://cdn.example'),
                 replace(self.config, azuracast_write_enabled=True, azuracast_url='http://radio.example'),
                 replace(self.config, azuracast_station='../2')]
        for config in cases:
            with self.assertRaises(ValueError):
                config.validate()


class HttpServerTests(unittest.TestCase):
    def test_hls_only_serves_generated_playlist_and_segments(self):
        from urllib.error import HTTPError
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hls = root / 'hls'
            hls.mkdir()
            name = 'segment-0123456789abcdef-00000000.aac'
            (hls / 'live.m3u8').write_text('#EXTM3U\n' + name + '\n')
            (hls / name).write_bytes(b'public audio segment')
            (hls / 'private.txt').write_text('private')
            server = LocalServer(root, 0)
            base = server.url.replace('player.html', '')
            try:
                for path, mime in [('hls/live.m3u8', 'application/vnd.apple.mpegurl'),
                                   ('hls/' + name, 'audio/aac')]:
                    with urlopen(base + path, timeout=3) as response:
                        self.assertEqual(response.headers['Content-Type'], mime)
                        self.assertEqual(response.headers['Cache-Control'], 'no-store')
                for path in ('hls/private.txt', 'hls/../config.json', 'hls/.encoder.lock'):
                    with self.assertRaises(HTTPError):
                        urlopen(base + path, timeout=3)
                (hls / name).unlink()
                try:
                    (hls / name).symlink_to(hls / 'private.txt')
                except OSError:
                    return
                with self.assertRaises(HTTPError):
                    urlopen(base + 'hls/' + name, timeout=3)
            finally:
                server.close()

    def test_service_serves_selected_metadata_but_never_config_or_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = Config(music_folders=[r'C:\Musica'], stale_seconds=300)
            decision = resolve([music(artwork=PNG)], config)
            state = LocalOutput(root).publish(decision, config)
            (root / 'config.json').write_text('{"password":"private"}')
            server = LocalServer(root, 0)
            try:
                with urlopen(server.url.replace('player.html', 'nowplaying.json'), timeout=3) as response:
                    self.assertEqual(json.load(response)['artist'], decision.song.artist)
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                with urlopen(server.url, timeout=3) as response:
                    html = response.read().decode()
                    self.assertIn('setInterval(paint', html)
                    self.assertIn('textContent', html)
                for suffix in ('config.json', '../config.json', '%2e%2e/config.json'):
                    from urllib.error import HTTPError
                    with self.assertRaises(HTTPError):
                        urlopen(server.url.replace('player.html', suffix), timeout=3)
                from urllib.error import HTTPError
                request = Request(server.url, headers={'Host': 'untrusted.example'})
                with self.assertRaises(HTTPError):
                    urlopen(request, timeout=3)
                with urlopen(server.url.replace('player.html', state['artwork_file']), timeout=3) as response:
                    self.assertEqual(response.headers['Content-Type'], 'image/png')
            finally:
                server.close()

class AdditionalBehaviorTests(unittest.TestCase):
    def test_operator_station_override_arriving_during_poll_wins(self):
        mode = ['auto']
        class Delayed:
            name = 'radioboss'
            async def poll(self):
                mode[0] = 'station'
                return music()
        with tempfile.TemporaryDirectory() as tmp:
            engine = Engine(Config(music_folders=[r'C:\Musica']), Path(tmp))
            engine.mode_provider = lambda: mode[0]
            with patch('radio_metadata.engine.make_sources', return_value=[Delayed()]):
                decision, _, _, rows = asyncio.run(engine.tick())
            self.assertIsNone(decision.song)
            self.assertEqual(decision.reason, 'Modo de pausa activado')
            self.assertEqual(rows, [])
            engine.close()

    def test_spotify_maps_real_smtc_property_names_without_inventing_year(self):
        from types import SimpleNamespace, ModuleType
        from radio_metadata.sources import SpotifyWindowsSource
        media = SimpleNamespace(playback_type='Music', thumbnail=None, artist='A', title='B',
                                album_title='Album', album_artist='AA', genres=['Rock'], track_number=2)
        async def properties():
            return media
        session = SimpleNamespace(source_app_user_model_id='Spotify.exe',
                                  get_playback_info=lambda: SimpleNamespace(playback_status='Playing'),
                                  try_get_media_properties_async=properties,
                                  get_timeline_properties=lambda: SimpleNamespace(start_time=timedelta(), end_time=timedelta(seconds=180), position=timedelta(seconds=10)))
        async def manager():
            return SimpleNamespace(get_sessions=lambda: [session])
        modules = {name: ModuleType(name) for name in ['winrt', 'winrt.windows', 'winrt.windows.media',
                   'winrt.windows.media.control', 'winrt.windows.storage', 'winrt.windows.storage.streams']}
        control = modules['winrt.windows.media.control']
        control.GlobalSystemMediaTransportControlsSessionManager = SimpleNamespace(request_async=manager)
        control.GlobalSystemMediaTransportControlsSessionPlaybackStatus = SimpleNamespace(PLAYING='Playing')
        modules['winrt.windows.media'].MediaPlaybackType = SimpleNamespace(MUSIC='Music')
        modules['winrt.windows.storage.streams'].DataReader = object
        with patch.dict('sys.modules', modules), patch('radio_metadata.sources.sys', SimpleNamespace(platform='win32')):
            track = asyncio.run(SpotifyWindowsSource(Config()).poll())
        self.assertEqual((track.album, track.album_artist, track.genre, track.track_number), ('Album', 'AA', 'Rock', 2))
        self.assertEqual((track.duration_ms, track.position_ms), (180000, 10000))
        self.assertEqual(track.year, '')
        self.assertEqual(track.isrc, '')
