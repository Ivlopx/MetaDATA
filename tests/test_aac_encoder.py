from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from radio_metadata.aac_encoder import (HLSSegments, check_ffmpeg, command_line,
                                       encode, id3_tags, synchsafe)
from radio_metadata.ogg_encoder import EncoderError, MetadataReader, transparent_png


def state(directory, **updates):
    value = dict(updated_at=datetime.now(timezone.utc).isoformat(), stale_seconds=300,
                 is_music=True, artist='Artista ñ', title='Canción', album='Álbum',
                 artwork_file='cover.png')
    value.update(updates)
    path = directory / 'nowplaying.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


def frames(tag):
    size = lambda data: sum(value << shift for value, shift in zip(data, (21, 14, 7, 0)))
    total = size(tag[6:10]) + 10
    assert total <= len(tag)
    offset, result = 10, {}
    while offset < total:
        name = tag[offset:offset + 4].decode()
        length = size(tag[offset + 4:offset + 8])
        result[name] = tag[offset + 10:offset + 10 + length]
        offset += 10 + length
    assert offset == total
    return result, total


class AACTests(unittest.TestCase):
    def test_id3_includes_utf8_picture_and_timestamp_and_clears_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            image = transparent_png()
            (directory / 'cover.png').write_bytes(image)
            reader = MetadataReader(state(directory, station='NEVER PUBLISH'))
            first, _ = frames(id3_tags(reader.read(), (1 << 33) + 90))
            self.assertEqual(first['TIT2'], b'\x03' + 'Canción'.encode())
            self.assertEqual(first['TALB'], b'\x03' + 'Álbum'.encode())
            self.assertTrue(first['APIC'].endswith(image))
            self.assertEqual(struct.unpack('>Q', first['PRIV'][-8:])[0], 90)
            state(directory, is_music=False, title='Advertisement', station='NEVER PUBLISH')
            paused = id3_tags(reader.read(), 100)
            tags, _ = frames(paused)
            self.assertEqual(tags['TIT2'], b'\x03')
            self.assertEqual(tags['TPE1'], b'\x03')
            self.assertNotIn(b'Advertisement', paused)
            self.assertNotIn(b'NEVER PUBLISH', paused)
            self.assertTrue(tags['APIC'].endswith(transparent_png()))
            self.assertEqual(synchsafe(128), b'\0\0\x01\0')

    def test_commands_select_correct_format_and_only_aac_can_generate_hls(self):
        aac = command_line('nowplaying.json', 'C:/Program Files/ffmpeg.exe', hls=True)
        self.assertIn('--format aac', aac)
        self.assertIn('--hls-dir', aac)
        self.assertIn('{SampleRate}', aac)
        mp3 = command_line('nowplaying.json', 'ffmpeg.exe', 'mp3')
        self.assertIn('--format mp3', mp3)
        self.assertNotIn('--hls-dir', mp3)
        general = command_line('nowplaying.json', 'ffmpeg', use_variables=False,
                               sample_rate=44100, channels=1, bitrate=96)
        self.assertNotIn('{', general)
        self.assertIn('--sample-rate 44100 --channels 1 --bitrate 96', general)
        with self.assertRaises(EncoderError):
            command_line('nowplaying.json', 'ffmpeg', 'mp3', True)
        with patch('radio_metadata.aac_encoder.subprocess.run',
                   return_value=subprocess.CompletedProcess([], 0, b' A..... aac Test\n')):
            check_ffmpeg('ffmpeg', 'aac')
            with self.assertRaises(EncoderError):
                check_ffmpeg('ffmpeg', 'mp3')

    def test_hls_rejects_garbage_and_concurrent_writers_without_deleting_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            writer = HLSSegments(directory / 'hls', state(directory))
            try:
                sentinel = directory / 'hls' / 'segment-aaaaaaaaaaaaaaaa-00000000.aac'
                sentinel.write_bytes(b'keep active')
                with self.assertRaises(EncoderError):
                    HLSSegments(directory / 'hls', directory / 'nowplaying.json')
                self.assertEqual(sentinel.read_bytes(), b'keep active')
                with self.assertRaises(EncoderError):
                    writer.feed(b'not AAC data')
            finally:
                writer.release()

    def test_hls_rolls_and_keeps_inflight_segments_and_changes_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = state(directory)
            writer = HLSSegments(directory / 'hls', path, seconds=.01, window=3)
            # Seven-byte ADTS header + one payload byte; enough to test the segmenter.
            packet = bytes.fromhex('fff14c80011ffc') + b'\0'
            try:
                writer.feed(packet[:3])
                writer.feed(packet[3:])
                first = next((directory / 'hls').glob('segment-*.aac'))
                self.assertEqual(frames(first.read_bytes())[0]['TIT2'], b'\x03' + 'Canción'.encode())
                state(directory, title='Segunda')
                writer.feed(packet)
                second = sorted((directory / 'hls').glob('segment-*.aac'))[-1]
                self.assertEqual(frames(second.read_bytes())[0]['TIT2'], b'\x03Segunda')
                writer.feed(packet * 10)
                playlist = (directory / 'hls/live.m3u8').read_text()
                names = [line for line in playlist.splitlines() if line.endswith('.aac')]
                self.assertEqual(len(names), 3)
                self.assertFalse(first.exists())
                self.assertLessEqual(len(list((directory / 'hls').glob('segment-*.aac'))), 7)
                self.assertTrue(all((directory / 'hls' / name).exists() for name in names))
                writer.close()
                self.assertIn('#EXT-X-ENDLIST', (directory / 'hls/live.m3u8').read_text())
            finally:
                writer.release()

    @unittest.skipUnless(os.environ.get('RADIO_AAC_TEST') == '1' and shutil.which('ffmpeg'), 'Requiere FFmpeg y RADIO_AAC_TEST=1')
    def test_real_aac_and_mp3_decode_and_hls_contains_actual_picture(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = state(directory)
            (directory / 'cover.png').write_bytes(transparent_png())
            samples = 48000 * 7
            pcm = b''.join(struct.pack('<h', int(8000 * math.sin(2 * math.pi * 440 * i / 48000))) * 2
                           for i in range(samples))
            for audio_format in ('aac', 'mp3'):
                result = io.BytesIO()
                encode(path, 48000, 2, 128, check_ffmpeg('', audio_format), audio_format,
                       directory / 'hls' if audio_format == 'aac' else None, io.BytesIO(pcm), result)
                output = directory / f'test.{audio_format}'
                output.write_bytes(result.getvalue())
                probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(output)],
                                       capture_output=True, check=True)
                info = json.loads(probe.stdout)['streams']
                self.assertEqual(info[0]['codec_name'], audio_format)
                self.assertNotIn(b'APIC', result.getvalue())
                decode = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(output), '-f', 's16le', 'pipe:1'],
                                        capture_output=True, check=True)
                self.assertGreater(len(decode.stdout), samples * 4 * .99)
                self.assertLess(len(decode.stdout), samples * 4 * 1.03)
            segments = sorted((directory / 'hls').glob('segment-*.aac'))
            self.assertEqual(len(segments), 2)
            for segment in segments:
                tags, offset = frames(segment.read_bytes())
                self.assertTrue(tags['APIC'].endswith(transparent_png()))
                self.assertEqual(segment.read_bytes()[offset:offset + 2], b'\xff\xf1')
                probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                        '-of', 'json', str(segment)], capture_output=True, check=True)
                info = json.loads(probe.stdout)
                self.assertEqual(info['format']['tags']['title'], 'Canción')
                self.assertTrue(any(stream.get('disposition', {}).get('attached_pic')
                                    for stream in info['streams']))
            # The HLS demuxer must accept the actual generated playlist, timestamps and AAC.
            decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(directory / 'hls/live.m3u8'),
                                      '-map', '0:a:0', '-f', 's16le', 'pipe:1'], capture_output=True)
            self.assertEqual(decoded.returncode, 0, decoded.stderr.decode())
            self.assertGreater(len(decoded.stdout), samples * 4 * .99)


if __name__ == '__main__':
    unittest.main()
