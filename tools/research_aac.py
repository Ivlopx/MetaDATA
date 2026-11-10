"""Isolated AAC/ID3 research fixtures; never connects to a production server.

Run from the repository root with Python and FFmpeg on PATH. The optional server
binds loopback only. Artifacts go to ignored work/aac-research by default.
"""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from shutil import copyfile
import struct
import subprocess
import sys
import time
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from radio_metadata.aac_encoder import HLSSegments, id3_tags
from radio_metadata.ogg_encoder import MetadataReader


def png(red, green, blue):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(bytes([0, red, green, blue, 255]))) + chunk(b'IEND', b'')


def generate(root, live=False):
    root.mkdir(parents=True, exist_ok=True)
    copyfile(Path(__file__).with_name('aac-hls-preview.html'), root / 'preview.html')
    path = root / 'nowplaying.json'
    for label, color in [('A', (220, 30, 30)), ('B', (30, 30, 220))]:
        (root / f'cover-{label}.png').write_bytes(png(*color))
    def update(label):
        path.write_text(json.dumps(dict(updated_at=datetime.now(timezone.utc).isoformat(), stale_seconds=300,
            is_music=bool(label), artist=f'Artist {label}' if label else '', title=f'Song {label}' if label else '',
            album=f'Album {label}' if label else '', artwork_file=f'cover-{label}.png' if label else '')), encoding='utf-8')
    update('A')
    reader = MetadataReader(path)
    writer = HLSSegments(root / 'hls', path, seconds=2 if live else 4)
    audio = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
                            '-t', '24' if live else '12', '-ac', '2', '-c:a', 'aac', '-b:a', '128k', '-f', 'adts', 'pipe:1'],
                            capture_output=True, check=True).stdout
    (root / 'plain.aac').write_bytes(audio)
    rich, offset, frame_number, previous = bytearray(), 0, 0, None
    pace_start = None
    while offset < len(audio):
        length = ((audio[offset + 3] & 3) << 11) | audio[offset + 4] << 3 | audio[offset + 5] >> 5
        elapsed = frame_number * 1024 / 48000
        if live:
            # Five initial segments let a client join the live playlist.
            # 94 AAC frames (1024 samples each) fit each 2-second segment.
            label = 'A' if frame_number < 470 else ('B' if frame_number < 752 else '')
            if frame_number >= 470:
                if pace_start is None:
                    pace_start = time.monotonic() - elapsed
                    print('Live playlist ready; open preview.html now.', flush=True)
                time.sleep(max(0, pace_start + elapsed - time.monotonic()))
        else:
            label = 'A' if elapsed < 4 else ('B' if elapsed < 8 else '')
        if label != previous:
            update(label)
            rich.extend(id3_tags(reader.read(), round(elapsed * 90000)))
            previous = label
        packet = audio[offset:offset + length]
        writer.feed(packet)
        rich.extend(packet)
        offset += length
        frame_number += 1
    writer.close()
    (root / 'rich.aac').write_bytes(rich)
    expected = {'audio_seconds': frame_number * 1024 / 48000,
                'states': ['Artist A / Song A / Album A / red cover',
                           'Artist B / Song B / Album B / blue cover',
                           'empty music fields / transparent cover'],
                'id3_markers_in_direct_fixture': rich.count(b'ID3\x04\0\0')}
    (root / 'fixture.json').write_text(json.dumps(expected, indent=2))
    print(json.dumps(expected), flush=True)


def serve(root, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            with (root / 'requests.jsonl').open('a') as out:
                out.write(json.dumps({'path': self.path, 'time': time.time()}) + '\n')
            relative = self.path.split('?')[0].lstrip('/')
            path = (root / relative).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Cache-Control', 'no-store')
            mime = ('audio/aac' if path.suffix == '.aac' else 'application/vnd.apple.mpegurl'
                    if path.suffix == '.m3u8' else 'text/html' if path.suffix == '.html' else
                    'text/javascript' if path.suffix == '.js' else 'application/octet-stream')
            self.send_header('Content-Type', mime)
            if relative != 'rich.aac':
                self.send_header('Content-Length', str(path.stat().st_size))
            self.end_headers()
            try:
                with path.open('rb') as source:
                    while data := source.read(512 if relative == 'rich.aac' else 65536):
                        self.wfile.write(data)
                        self.wfile.flush()
                        if relative == 'rich.aac':
                            time.sleep(len(data) / 16000)
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'Listening: http://127.0.0.1:{server.server_port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('work/aac-research'))
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--live', action='store_true', help='Warm up a playlist, then generate rolling segments in real time')
    parser.add_argument('--port', type=int, default=18089)
    args = parser.parse_args()
    if args.serve:
        serve(args.directory, args.port)
    else:
        generate(args.directory, live=args.live)


if __name__ == '__main__':
    main()
