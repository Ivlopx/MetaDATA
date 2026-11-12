import asyncio
from dataclasses import replace
import io
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave

import httpx

from radio_metadata.config import Config
from radio_metadata.credentials import MemoryCredentials
from radio_metadata.engine import Engine
from radio_metadata.model import Snapshot, resolve
from radio_metadata.monitoring import (pcm_levels, probe_audio, probe_statistics, MonitorHistory,
                                       BroadcastMonitor, stats_key)
from radio_metadata.outputs import LocalOutput


class TitleFormatTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(spotify_publish=True)
        self.song = Snapshot('spotify', True, 'Artista', 'Canción', kind='music', album='Álbum')

    def test_order_template_and_structured_fields_remain_independent(self):
        self.assertEqual(resolve([self.song], self.config).text, 'Canción - Artista')
        self.config.title_format = '{artist} - {title}'
        self.assertEqual(resolve([self.song], self.config).text, 'Artista - Canción')
        self.config.title_format = '{title} | {artist} | {album}'
        with tempfile.TemporaryDirectory() as tmp:
            state = LocalOutput(Path(tmp)).publish(resolve([self.song], self.config), self.config)
        self.assertEqual(state['display_text'], 'Canción | Artista | Álbum')
        self.assertEqual(state['text'], 'Artista - Canción')
        self.assertEqual((state['artist'], state['title'], state['album']), ('Artista', 'Canción', 'Álbum'))
        self.assertEqual(resolve([replace(self.song, title='Publicidad')], self.config).song, None)

    def test_unsafe_or_invalid_template_is_rejected(self):
        for template in ('{artist}', '{title.__class__}', '{title[0]}', '{title!r}', '{title:>100}', '{unknown}', '{title', '{title}\n{artist}'):
            with self.assertRaises(ValueError, msg=template):
                replace(self.config, title_format=template).validate()
        replace(self.config, title_format='{{{title}}} - {artist}').validate()


class AudioMonitorTests(unittest.TestCase):
    def test_sustained_silence_not_overall_loudness(self):
        sine = b''.join(struct.pack('<h', int(8000 * math.sin(i * 2 * math.pi * 440 / 8000))) for i in range(8000))
        rms, silence, duration = pcm_levels(sine + b'\0' * 64000 + sine)
        self.assertGreater(rms, -30)
        self.assertAlmostEqual(silence, 4, places=2)
        self.assertEqual(duration, 6)
        self.assertEqual(pcm_levels(b'\0' * 80000)[0], -120)
        # Opposite stereo phase must not cancel out and be mistaken for silence.
        stereo = struct.pack('<hh', 8000, -8000) * 8000
        self.assertEqual(pcm_levels(stereo, channels=2)[1:], (0., 1.))
        with self.assertRaises(ValueError):
            pcm_levels(b'')

    def test_probe_timeout_or_partial_samples_are_errors(self):
        config = Config(stream_url='https://audio.example/live.aac')
        with patch('radio_metadata.ogg_encoder.find_ffmpeg', return_value='ffmpeg'), \
             patch('radio_metadata.monitoring.subprocess.run', side_effect=subprocess.TimeoutExpired('ffmpeg', 13)):
            self.assertEqual(probe_audio(config)['state'], 'error')
        with patch('radio_metadata.ogg_encoder.find_ffmpeg', return_value='ffmpeg'), \
             patch('radio_metadata.monitoring.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'\0' * 200)):
            self.assertEqual(probe_audio(config)['state'], 'error')

    @unittest.skipUnless(os.environ.get('RADIO_AAC_TEST') == '1' and shutil.which('ffmpeg'), 'Requiere FFmpeg')
    def test_real_ffmpeg_http_audio_and_silence(self):
        from functools import partial
        from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, data in [('silence', b'\0' * 80000), ('tone', b''.join(struct.pack('<h', int(6000 * math.sin(i * 2 * math.pi * 440 / 8000))) for i in range(40000)))]:
                with wave.open(str(root / (name + '.wav')), 'wb') as stream:
                    stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8000); stream.writeframes(data)
            server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=tmp))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                config = Config(stream_url=f'http://127.0.0.1:{server.server_port}/tone.wav')
                self.assertEqual(probe_audio(config)['state'], 'ok')
                config.stream_url = f'http://127.0.0.1:{server.server_port}/silence.wav'
                self.assertEqual(probe_audio(config)['state'], 'silence')
            finally:
                server.shutdown();server.server_close();thread.join()

    def test_background_probe_does_not_hold_metadata_worker(self):
        event = threading.Event()
        def blocked(config):
            event.wait(2)
            return dict(channel='audio', state='ok', message='Audio recibido')
        monitor = BroadcastMonitor(Config(audio_monitor_enabled=True, stream_url='https://audio.example/live.aac'), MemoryCredentials())
        try:
            with patch('radio_metadata.monitoring.probe_audio', side_effect=blocked):
                start = time.monotonic()
                records, done = monitor.poll()
                self.assertLess(time.monotonic() - start, .5)
                self.assertEqual(done, [])
                event.set()
                for future in monitor.jobs.values():
                    future.result(timeout=2)
                records, done = monitor.poll()
                self.assertEqual(done[0]['state'], 'ok')
        finally:
            event.set(); monitor.close()


class MonitorStatisticsTests(unittest.TestCase):
    def test_server_counts_authorization_and_missing_is_not_zero(self):
        config = Config(statistics_url='https://stats.example/current')
        vault = MemoryCredentials();vault.set(stats_key(config), 'test-bearer-token')
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'listeners': 0})
        factory = httpx.Client
        with patch('radio_metadata.monitoring.httpx.Client', side_effect=lambda **kw: factory(transport=httpx.MockTransport(handler), **kw)):
            result = probe_statistics(config, vault)
        self.assertEqual((result['state'], result['listeners']), ('ok', 0))
        self.assertEqual(requests[0].headers['Authorization'], 'Bearer test-bearer-token')
        with patch('radio_metadata.monitoring.read_json', return_value={'listeners': True}):
            result = probe_statistics(config, vault)
        self.assertEqual((result['state'], result['listeners']), ('error', None))

    def test_icecast_mount_and_azuracast_reads_are_optional(self):
        config = Config(statistics_url='https://stats.example/current', statistics_format='icecast', statistics_mount='/live.aac')
        data = {'icestats': {'source': [{'listenurl': 'https://audio.example/other.aac', 'listeners': 900},
                                      {'listenurl': 'https://audio.example/live.aac', 'listeners': '12'}]}}
        with patch('radio_metadata.monitoring.read_json', return_value=data):
            self.assertEqual(probe_statistics(config, MemoryCredentials())['listeners'], 12)
        config.statistics_format = 'azuracast'
        with patch('radio_metadata.monitoring.read_json', return_value={'is_online': True, 'listeners': {'current': 7}}):
            self.assertEqual(probe_statistics(config, MemoryCredentials())['listeners'], 7)

    def test_incident_confirmation_recovery_retention_and_scope(self):
        config = Config(statistics_enabled=True, statistics_url='https://stats.example/current', monitor_confirmations=2)
        bad = dict(channel='audio', state='silence', message='Silencio')
        good = dict(channel='audio', state='ok', message='Audio')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'monitor.sqlite3'
            history = MonitorHistory(path)
            history.configure_scope(config)
            history.record([bad], config)
            self.assertEqual(len(history.view()['incidents']), 0)
            history.record([bad, bad], config)
            self.assertEqual(len(history.view()['incidents']), 1)
            history.record([good], config)
            self.assertIsNone(history.view()['incidents'][0][1])
            history.record([good], config)
            self.assertIsNotNone(history.view()['incidents'][0][1])
            history.record([dict(channel='statistics', state='ok', listeners=n, message='OK') for n in (0, 10, 20)], config)
            history.record([dict(channel='statistics', state='error', listeners=None, message='Error')], config)
            self.assertEqual(history.view()['summary'], (3, 20, 10))
            config.statistics_url = 'https://stats.example/other'
            history.configure_scope(config)
            self.assertEqual(history.view()['summary'][0], 0)
            history.db.execute("UPDATE monitor_samples SET checked_at='2000-01-01T00:00:00+00:00'")
            history.db.commit()
            history.record([good], config)
            self.assertEqual(history.db.execute('SELECT COUNT(*) FROM monitor_samples').fetchone()[0], 1)
            history.close()
            restored = MonitorHistory(path);restored.configure_scope(config)
            self.assertEqual(len(restored.view()['incidents']), 1)
            restored.close()

    def test_engine_demo_never_starts_real_monitor_or_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Config(audio_monitor_enabled=True, stream_url='https://audio.example/live.aac', statistics_enabled=True,
                            statistics_url='https://stats.example/current')
            engine = Engine(config, Path(tmp), demo=True)
            try:
                with patch('radio_metadata.monitoring.probe_audio') as audio, patch('radio_metadata.monitoring.probe_statistics') as stats:
                    asyncio.run(engine.tick())
                    self.assertIsNone(engine.monitor)
                    audio.assert_not_called();stats.assert_not_called()
            finally:
                engine.close()

class BroadcastTitleCompatibilityTests(unittest.TestCase):
    def test_visual_order_never_changes_default_emitter_parser_fields(self):
        import xml.etree.ElementTree as ET
        song = Snapshot('spotify', True, 'Artist example', 'Track example', kind='music')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for visual in ('{title} - {artist}', '{title}', '{title} | {artist}'):
                config = Config(spotify_publish=True, title_format=visual)
                state = LocalOutput(root).publish(resolve([song], config), config)
                track = ET.fromstring((root / 'nowplaying.xml').read_bytes()).find('TRACK')
                parsed_artist, parsed_title = track.get('CASTTITLE').split(' - ', 1)
                self.assertEqual((parsed_artist, parsed_title), (song.artist, song.title))
                self.assertEqual(track.get('DISPLAYTITLE'), state['display_text'])
                self.assertEqual(track.get('ARTIST'), song.artist)
                self.assertEqual(track.get('TITLE'), song.title)
                self.assertEqual((root / 'nowplaying.txt').read_text().strip(), 'Artist example - Track example')
                state = LocalOutput(root).publish(resolve([], config), config)
                track = ET.fromstring((root / 'nowplaying.xml').read_bytes()).find('TRACK')
                self.assertEqual((track.get('CASTTITLE'), track.get('DISPLAYTITLE'), state['display_text']), ('', '', ''))

    def test_old_configuration_gets_compatible_emitter_default_without_losing_visual_choice(self):
        from dataclasses import asdict
        from radio_metadata.config import ConfigStore
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp))
            values = asdict(Config(title_format='{title} | {artist}'))
            values.pop('broadcast_title_format')
            store.path.write_text(json.dumps(values))
            loaded = store.load()
            self.assertEqual(loaded.title_format, '{title} | {artist}')
            self.assertEqual(loaded.broadcast_title_format, '{artist} - {title}')
            with self.assertRaises(ValueError):
                replace(loaded, broadcast_title_format='{title.__class__}').validate()
