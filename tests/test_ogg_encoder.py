import base64
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

from radio_metadata.ogg_encoder import (MetadataReader, CLEAR_PICTURE, EncoderError, check_ffmpeg,
                                       command_line, metadata_bytes, transparent_png, encode)


class OggEncoderTests(unittest.TestCase):
    def state(self, directory, **updates):
        value = {'updated_at': datetime.now(timezone.utc).isoformat(), 'stale_seconds': 30,
                 'is_music': True, 'artist': 'Artista', 'title': 'Canción', 'album': 'Álbum',
                 'genre': 'Pop', 'year': '2026', 'artwork_file': 'cover.png',
                 'station': 'Never use as a song', 'display_message': 'Private station text'}
        value.update(updates)
        path = directory / 'nowplaying.json'
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return path

    def test_metadata_and_picture_are_embedded_without_station_identity_or_private_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            # Known valid PNG, sufficiently different from the transparent clearing pixel.
            image = transparent_png() + b'test-unique'
            (directory / 'cover.png').write_bytes(image)
            reader = MetadataReader(self.state(directory, filename='C:\\Private\\song.mp3'))
            tags = reader.read()
            self.assertEqual(tags['artist'], 'Artista')
            self.assertEqual(tags['album'], 'Álbum')
            self.assertEqual(tags['date'], '2026')
            self.assertTrue(base64.b64decode(tags['METADATA_BLOCK_PICTURE']).endswith(image))
            self.assertNotIn('Private', metadata_bytes(tags).decode())
            self.assertNotIn('Never use', metadata_bytes(tags).decode())

    def test_pause_stale_future_invalid_and_missing_fields_clear_all_music_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for updates in [dict(is_music=False), dict(artist=''), dict(title=''), dict(is_music='true'),
                            dict(updated_at=(datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()),
                            dict(updated_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()),
                            dict(updated_at='invalid'), dict(stale_seconds='30')]:
                tags = MetadataReader(self.state(directory, **updates)).read()
                self.assertTrue(all(tags[key] == '' for key in ('artist', 'title', 'album', 'album_artist', 'genre', 'date')))
                self.assertEqual(tags['METADATA_BLOCK_PICTURE'], CLEAR_PICTURE)
            path = directory / 'nowplaying.json'
            path.write_text('{broken', encoding='utf-8')
            self.assertEqual(MetadataReader(path).read()['METADATA_BLOCK_PICTURE'], CLEAR_PICTURE)

    def test_reader_follows_atomic_state_changes_and_image_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = self.state(directory)
            reader = MetadataReader(path)
            self.assertEqual(reader.read()['title'], 'Canción')
            replacement = directory / 'next.json'
            replacement.write_text(json.dumps({'updated_at': datetime.now(timezone.utc).isoformat(),
                'stale_seconds': 30, 'is_music': True, 'artist': 'Otro', 'title': 'Otra', 'album': 'Segundo'}))
            os.replace(replacement, path)
            self.assertEqual(reader.read()['title'], 'Otra')
            (directory / 'cover.png').write_bytes(transparent_png() + b'A')
            self.state(directory)
            first = reader.read()['METADATA_BLOCK_PICTURE']
            (directory / 'cover.png').write_bytes(transparent_png() + b'BB')
            self.assertNotEqual(reader.read()['METADATA_BLOCK_PICTURE'], first)

    def test_asset_paths_cannot_escape_the_export_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            outside = directory / 'outside.png'
            outside.write_bytes(transparent_png() + b'private')
            exports = directory / 'export'; exports.mkdir()
            for name in ['../outside.png', str(outside), '..\\outside.png']:
                self.assertEqual(MetadataReader(self.state(exports, artwork_file=name)).read()['METADATA_BLOCK_PICTURE'], CLEAR_PICTURE)
            try:
                (exports / 'link.png').symlink_to(outside)
            except OSError:
                return
            self.assertEqual(MetadataReader(self.state(exports, artwork_file='link.png')).read()['METADATA_BLOCK_PICTURE'], CLEAR_PICTURE)

    def test_missing_or_unsupported_cover_replaces_previous_cover(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'cover.webp').write_bytes(b'RIFFxxxxWEBPtest')
            for name in ('missing.png', 'cover.webp', ''):
                tags = MetadataReader(self.state(directory, artwork_file=name)).read()
                self.assertEqual(tags['title'], 'Canción')
                self.assertEqual(tags['METADATA_BLOCK_PICTURE'], CLEAR_PICTURE)

    def test_transparent_cover_is_actually_a_transparent_pixel(self):
        image = transparent_png()
        self.assertEqual(struct.unpack('>IIBB', image[16:26]), (1, 1, 8, 6))
        offset, compressed = 8, b''
        while offset < len(image):
            length = struct.unpack_from('>I', image, offset)[0]
            if image[offset + 4:offset + 8] == b'IDAT':
                compressed += image[offset + 8:offset + 8 + length]
            offset += length + 12
        self.assertEqual(zlib.decompress(compressed), b'\0\0\0\0\0')

    def test_ffmetadata_escapes_control_characters_and_never_uses_a_shell(self):
        data = metadata_bytes({'title': 'A=B;#C\\D\nE\rF'})
        self.assertIn(b'A\\=B\\;\\#C\\\\D\\\nEF', data)
        self.assertNotIn(b'\r', data)
        with patch('radio_metadata.ogg_encoder.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b' A.... libopus\n', b'')) as run:
            check_ffmpeg('C:/Program Files/FFmpeg/ffmpeg.exe')
            self.assertIsInstance(run.call_args.args[0], list)
            self.assertFalse(run.call_args.kwargs.get('shell', False))
        with patch('radio_metadata.ogg_encoder.subprocess.run', side_effect=OSError('secret-error-data')):
            with self.assertRaises(EncoderError) as raised:
                check_ffmpeg('missing')
            self.assertNotIn('secret-error-data', str(raised.exception))

    def test_command_preserves_radiocaster_placeholders_and_quotes_spaces(self):
        line = command_line(Path('C:/My Radio/nowplaying.json'), 'C:/Program Files/FFmpeg/ffmpeg.exe')
        for marker in ('{SampleRate}', '{Channels}', '{Bitrate}'):
            self.assertIn(marker, line)
        self.assertIn('"C:/Program Files/FFmpeg/ffmpeg.exe"', line)
        self.assertIn('-m radio_metadata.ogg_encoder', line)
        self.assertNotIn('password', line)

    @unittest.skipUnless(os.environ.get('RADIO_OGG_TEST') == '1' and shutil.which('ffmpeg'), 'Activar RADIO_OGG_TEST=1 con FFmpeg/libopus')
    def test_real_encoder_outputs_audio_and_picture_and_accepts_44100_pcm(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = self.state(directory)
            encoded = io.BytesIO()
            samples = 4410
            encode(path, 44100, 2, 128, check_ffmpeg(), io.BytesIO(b'\0' * samples * 4), encoded)
            data = encoded.getvalue()
            self.assertIn(b'OpusHead', data)
            self.assertIn(b'OpusTags', data)
            self.assertIn(b'artist=Artista', data)
            self.assertIn(b'METADATA_BLOCK_PICTURE=', data)
            file = directory / 'result.opus'; file.write_bytes(data)
            decoded = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(file), '-map', '0:a:0',
                '-f', 's16le', '-ar', '44100', '-ac', '2', 'pipe:1'], capture_output=True, check=True)
            self.assertEqual(len(decoded.stdout), samples * 4)
