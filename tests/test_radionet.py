import asyncio
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from radio_metadata.config import Config
from radio_metadata.credentials import MemoryCredentials, secret_id
from radio_metadata.engine import Engine
from radio_metadata.model import Decision, Snapshot


class RadioNetTests(unittest.TestCase):
    def test_engine_publishes_changes_and_reports_api_errors_without_repeating(self):
        config = Config(radionet_enabled=True, radionet_slug='example-station')
        credentials = MemoryCredentials()
        credentials.set(secret_id('radionet', config.radionet_slug), 'test-key')
        track = Snapshot('test', artist='Banda & Sol', title='Canción + Luz', album='Álbum')
        song = Decision('Texto combinado', 'test', '', track)
        pause = Decision('Descripción local', 'test', '')
        requests = []
        codes = iter([0, 7, 0])
        client = httpx.Client

        def handle(request):
            requests.append(request)
            return httpx.Response(200, json={'errorCode': next(codes)})

        with TemporaryDirectory() as directory, patch(
            'radio_metadata.radionet.httpx.Client',
            side_effect=lambda **kwargs: client(transport=httpx.MockTransport(handle), **kwargs),
        ):
            engine = Engine(config, Path(directory), credentials=credentials)
            try:
                self.assertIn('radio.net: canción aceptada', asyncio.run(engine.publish(song)))
                engine.configure(replace(config, station_name='Otro nombre'))
                asyncio.run(engine.publish(song))
                self.assertIn('radio.net: el servidor rechazó el envío', asyncio.run(engine.publish(pause)))
                asyncio.run(engine.publish(pause))
                asyncio.run(engine.publish(song))
            finally:
                engine.close()

        first, commercial, resumed = requests
        self.assertEqual(first.method, 'GET')
        self.assertEqual(first.url.scheme, 'https')
        self.assertEqual(first.url.host, 'api.radio.de')
        self.assertEqual(first.url.path, '/info/v2/pushmetadata/playingsong')
        self.assertEqual(dict(first.url.params), {
            'broadcast': 'example-station', 'apikey': 'test-key',
            'artist': 'Banda & Sol', 'title': 'Canción + Luz', 'album': 'Álbum',
        })
        self.assertEqual(dict(commercial.url.params), {
            'broadcast': 'example-station', 'apikey': 'test-key', 'commercial': 'true',
        })
        self.assertEqual(resumed.url, first.url)
