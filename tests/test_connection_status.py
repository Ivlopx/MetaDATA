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

    def test_file_success_never_claims_broadcast_connection(self):
        states = connection_states(Config(), [], [], [], local_exists=True)
        self.assertEqual(states['Now Playing'][0], 'warning')
        self.assertIn('sin comprobar', states['Now Playing'][1])
        self.assertEqual(set(states), {'RadioBOSS', 'Spotify', 'Now Playing', 'Receptor'})
        failed = connection_states(Config(), [], ['Error de salida local: prueba'], [], local_exists=True)
        self.assertEqual(failed['Now Playing'][0], 'error')

    def test_legacy_remote_settings_do_not_restore_removed_connections(self):
        config = Config(remote_monitor_enabled=True)
        record = dict(service='AzuraCast', online=True, error='', matches=True)
        self.assertEqual(set(connection_states(config, [], [], [record])), {'RadioBOSS', 'Spotify', 'Now Playing', 'Receptor'})

    def test_demo_and_paused_metadata_do_not_claim_live_connections(self):
        config = Config(radioboss_enabled=True)
        track = Snapshot('radioboss', True, available=True)
        self.assertEqual(connection_states(config, [track], [], [], demo=True)['RadioBOSS'][0], 'unknown')
        self.assertEqual(connection_states(config, [track], [], [], mode='station')['RadioBOSS'][0], 'unknown')
