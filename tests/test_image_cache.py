from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from radio_metadata.config import Config
from radio_metadata.image_cache import asset_name, owned_files, cache_usage
from radio_metadata.model import Snapshot, resolve
from radio_metadata.ogg_encoder import transparent_png, MetadataReader
from radio_metadata.outputs import LocalOutput
from radio_metadata.storage import History

PNG = transparent_png()


class CoverCacheTests(unittest.TestCase):
    def test_visible_history_controls_retained_images_without_deleting_history_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = History(root / 'history.sqlite3')
            output = LocalOutput(root / 'output')
            config = Config(spotify_publish=True, history_visible_limit=10)
            names = []
            try:
                for index in range(15):
                    image = PNG + str(index).encode()
                    track = Snapshot('spotify', True, 'Artista', f'Canción {index}', kind='music', artwork=image)
                    decision = resolve([track], config)
                    history.record(decision)
                    state = output.publish(decision, config, history.recent_artwork_files(10))
                    names.append(state['artwork_file'])
                self.assertEqual(len(owned_files(output.directory / 'covers')), 10)
                self.assertFalse((output.directory / names[0]).exists())
                self.assertTrue((output.directory / names[-1]).exists())
                self.assertEqual(history.db.execute('SELECT COUNT(*) FROM songs').fetchone()[0], 15)
                self.assertEqual(len(history.recent(10)), 10)
                for suffix in ('txt', 'xml', 'json'):
                    self.assertTrue((output.directory / ('nowplaying.' + suffix)).exists())
                self.assertFalse(list(output.directory.glob('artwork-*')))
            finally:
                history.close()

    def test_repeated_covers_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = History(root / 'history.sqlite3')
            output = LocalOutput(root / 'output')
            config = Config(spotify_publish=True)
            try:
                for title in ('Primera', 'Segunda'):
                    decision = resolve([Snapshot('spotify', True, 'Artista', title, kind='music', artwork=PNG)], config)
                    history.record(decision)
                    output.publish(decision, config, history.recent_artwork_files())
                self.assertEqual(cache_usage(output.directory)[0], 1)
                self.assertEqual(len(history.recent()), 2)
            finally:
                history.close()

    def test_current_cover_and_logo_survive_size_limit_and_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logo = root / 'logo.png'
            logo.write_bytes(PNG + b'L' * (3 * 1024 * 1024))
            config = Config(spotify_publish=True, logo_path=str(logo), cover_cache_mb=8)
            output = LocalOutput(root / 'output')
            old_image = PNG + b'X' * (2 * 1024 * 1024)
            previous = resolve([Snapshot('spotify', True, 'A', 'Anterior', kind='music', artwork=old_image)], config)
            old_state = output.publish(previous, config)
            new_image = PNG + b'N' * (3 * 1024 * 1024)
            current = resolve([Snapshot('spotify', True, 'A', 'Actual', kind='music', artwork=new_image)], config)
            state = output.publish(current, config, [asset_name(new_image), asset_name(old_image)])
            self.assertTrue((output.directory / state['artwork_file']).exists())
            self.assertTrue((output.directory / state['logo_file']).exists())
            self.assertFalse((output.directory / old_state['artwork_file']).exists())
            self.assertLessEqual(cache_usage(output.directory)[1], 8 * 1024 * 1024)
            output.publish(resolve([], config), config, [state['artwork_file']])
            self.assertTrue((output.directory / state['artwork_file']).exists())
            self.assertTrue((output.directory / state['logo_file']).exists())

    def test_moves_only_owned_legacy_images_and_encoder_reads_covers_subfolder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = asset_name(PNG)
            old = root / Path(expected).name
            old.write_bytes(PNG)
            other = root / 'my-personal-photo.png'
            other.write_bytes(PNG)
            config = Config(spotify_publish=True)
            decision = resolve([Snapshot('spotify', True, 'A', 'Canción', kind='music', artwork=PNG)], config)
            state = LocalOutput(root).publish(decision, config)
            self.assertFalse(old.exists())
            self.assertEqual((root / expected).read_bytes(), PNG)
            self.assertTrue(other.exists())
            tags = MetadataReader(root / 'nowplaying.json').read()
            self.assertEqual(tags['title'], 'Canción')
            self.assertTrue(state['artwork_file'].startswith('covers/'))

    def test_history_and_cache_limits_are_validated(self):
        for values in (dict(history_visible_limit=0), dict(history_visible_limit=1001), dict(cover_cache_mb=1)):
            with self.assertRaises(ValueError):
                Config(**values).validate()
