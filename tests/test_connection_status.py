import unittest
from radio_metadata.config import Config
from radio_metadata.connection_status import connection_states
from radio_metadata.model import Snapshot


class ConnectionStatusTests(unittest.TestCase):
    def test_connected_paused_is_distinct_from_unavailable_and_disabled(self):
        config = Config(radioboss_enabled=True, spotify_enabled=True)
        states = connection_states(config, [Snapshot('radioboss', available=True), Snapshot('spotify', available=False)], [], [])
        self.assertEqual(states['RadioBOSS'][0], 'ok')
        self.assertIn('pausa', states['RadioBOSS'][1])
        self.assertEqual(states['Spotify'][0], 'error')
        config.spotify_enabled = False
        self.assertEqual(connection_states(config, [], [], [])['Spotify'], ('unknown', 'Desactivado'))

    def test_file_success_never_claims_encoder_or_zeno_connection(self):
        states = connection_states(Config(), [], [], [], local_exists=True)
        self.assertEqual(states['RadioCaster'][0], 'warning')
        self.assertIn('sin comprobar', states['RadioCaster'][1])
        self.assertEqual(states['Zeno.fm'][0], 'unknown')
        failed = connection_states(Config(), [], ['Error de salida local: prueba'], [], local_exists=True)
        self.assertEqual(failed['RadioCaster'][0], 'error')

    def test_remote_states_use_actual_observation_and_detect_mismatch(self):
        config = Config(remote_monitor_enabled=True)
        record = dict(service='AzuraCast', online=True, error='', matches=True)
        self.assertEqual(connection_states(config, [], [], [record])['AzuraCast'][0], 'ok')
        record['matches'] = False
        self.assertEqual(connection_states(config, [], [], [record])['AzuraCast'][0], 'warning')
        record['error'] = 'HTTPStatusError'
        self.assertEqual(connection_states(config, [], [], [record])['AzuraCast'][0], 'error')

    def test_demo_and_paused_metadata_do_not_claim_live_connections(self):
        config = Config(radioboss_enabled=True)
        track = Snapshot('radioboss', True, available=True)
        self.assertEqual(connection_states(config, [track], [], [], demo=True)['RadioBOSS'][0], 'unknown')
        self.assertEqual(connection_states(config, [track], [], [], mode='station')['RadioBOSS'][0], 'unknown')
