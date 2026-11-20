from dataclasses import replace
import unittest
from unittest.mock import patch

import httpx

from radio_metadata.config import Config
from radio_metadata.credentials import MemoryCredentials
from radio_metadata.model import Decision, Snapshot
from radio_metadata.tunein import TuneInOutput, tunein_key

HttpClient = httpx.Client


class TuneInTests(unittest.TestCase):
    def setUp(self):
        config = Config(tunein_enabled=True, tunein_station_id='s123', tunein_partner_id='partner')
        credentials = MemoryCredentials()
        credentials.set(tunein_key(config), 'test-key')
        self.output = TuneInOutput(config, credentials)
        self.song = Decision('Artista - Título', 'demo', '', Snapshot('demo', artist='Artista', title='Título', album='Álbum'))
        self.pause = Decision('Descripción local', 'demo', '')
        self.requests = []

    def client(self, statuses, **kwargs):
        def handle(request):
            self.requests.append(request)
            return httpx.Response(next(statuses))

        return HttpClient(transport=httpx.MockTransport(handle), **kwargs)

    def test_sends_each_transition_once_with_the_right_fields(self):
        statuses = iter([200, 200, 200])
        with patch('radio_metadata.tunein.httpx.Client', side_effect=lambda **kw: self.client(statuses, **kw)):
            self.output.send(self.song)
            self.output.send(replace(self.song, song=replace(self.song.song, position_ms=2000)))
            self.output.send(self.pause)
            self.output.send(self.pause)
            self.output.send(self.song)

        self.assertEqual(len(self.requests), 3)
        first, pause, resumed = (request.url.params for request in self.requests)
        self.assertEqual(first['title'], 'Título')
        self.assertEqual(first['artist'], 'Artista')
        self.assertEqual(first['album'], 'Álbum')
        self.assertEqual(pause['commercial'], 'true')
        self.assertNotIn('title', pause)
        self.assertEqual(resumed, first)

    def test_retries_current_state_instead_of_sending_stale_song(self):
        statuses = iter([429, 200])
        with (
            patch('radio_metadata.tunein.httpx.Client', side_effect=lambda **kw: self.client(statuses, **kw)),
            patch('radio_metadata.tunein.time.monotonic', return_value=100) as clock,
        ):
            self.assertIn('429', self.output.send(self.song))
            self.output.send(self.pause)
            self.assertEqual(len(self.requests), 1)
            clock.return_value = 131
            self.assertIn('pausa aceptada', self.output.send(self.pause))
        self.assertNotIn('title', self.requests[-1].url.params)
        self.assertEqual(self.requests[-1].url.params['commercial'], 'true')
