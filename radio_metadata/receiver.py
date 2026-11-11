"""Small single-publisher receiver. Run behind an HTTPS reverse proxy."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
import time

from .config import atomic_write
from .image_cache import image_type

MAX_BODY = 6 * 1024 * 1024
TEXT_FIELDS = ('text', 'artist', 'title', 'album', 'album_artist', 'year', 'genre', 'isrc',
               'source', 'station', 'description', 'website', 'station_genre', 'stream_url')
SONG_FIELDS = ('text', 'artist', 'title', 'album', 'album_artist', 'year', 'genre', 'isrc', 'source')
NUMBER_FIELDS = ('duration_ms', 'position_ms', 'track_number')


def normalize(state):
    if not isinstance(state, dict) or type(state.get('is_music')) is not bool:
        raise ValueError('Invalid state')
    result = {'schema_version': 1, 'is_music': state['is_music']}
    for field in TEXT_FIELDS:
        value = state.get(field, '')
        if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
            raise ValueError('Invalid field')
        result[field] = value.strip()
    for field in NUMBER_FIELDS:
        value = state.get(field)
        if value is not None and (type(value) is not int or not 0 <= value <= 2**53):
            raise ValueError('Invalid number')
        result[field] = value
    if result['is_music'] and not (result['artist'] and result['title']):
        raise ValueError('Music needs artist and title')
    if not result['is_music']:
        for field in SONG_FIELDS:
            result[field] = ''
        for field in NUMBER_FIELDS:
            result[field] = None
    return result


class ReceiverStore:
    def __init__(self, directory, ttl=45):
        if type(ttl) is not int or not 15 <= ttl <= 300:
            raise ValueError('TTL: 15–300 seconds')
        self.path = Path(directory) / 'current.json'
        self.ttl = ttl
        self.lock = threading.RLock()
        self.current = None
        if self.path.exists():
            if self.path.stat().st_size > MAX_BODY:
                raise ValueError('Stored state too large')
            self.current = json.loads(self.path.read_bytes())

    def put(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('Invalid request')
        state = normalize(payload.get('state'))
        encoded = payload.get('artwork_base64', '')
        if not isinstance(encoded, str) or len(encoded) > 5600000:
            raise ValueError('Invalid image')
        art = base64.b64decode(encoded, validate=True)
        if art and not image_type(art):
            raise ValueError('Unsupported image')
        if not state['is_music']:
            art, encoded = b'', ''
        digest = hashlib.sha256(art).hexdigest() if art else ''
        state['artwork_url'] = '/artwork/' + digest if art else ''
        revision = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
        state['revision'] = revision
        with self.lock:
            record = dict(state=state, image=encoded, received_at=time.time())
            atomic_write(self.path, json.dumps(record).encode())
            self.current = record
        return revision

    def heartbeat(self, revision):
        with self.lock:
            if not self.current or revision != self.current['state']['revision']:
                return False
            record = dict(self.current, received_at=time.time())
            atomic_write(self.path, json.dumps(record).encode())
            self.current = record
            return True

    def snapshot(self):
        with self.lock:
            current = self.current
            expired = not current or time.time() - current['received_at'] > self.ttl
            if expired:
                state = normalize(dict(current['state'], is_music=False) if current else {'is_music': False})
                state.update(artwork_url='', revision='', expired=True)
                return state, b''
            state = dict(current['state'], expired=False)
            state['updated_at'] = datetime.fromtimestamp(current['received_at'], timezone.utc).isoformat()
            state['stale_seconds'] = self.ttl
            return state, base64.b64decode(current['image'])


class ReceiverServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, directory, token, ttl=45):
        if not isinstance(token, str) or len(token) < 32 or any(ord(c) > 126 or ord(c) < 33 for c in token):
            raise ValueError('Use a publication key of at least 32 ASCII characters')
        self.store = ReceiverStore(directory, ttl)
        self.token = token
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(address, ReceiverHandler)

    def process_request(self, request, address):
        self.slots.acquire()
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class ReceiverHandler(BaseHTTPRequestHandler):
    server_version = 'MetaDATA Receiver'

    def setup(self):
        super().setup()
        self.connection.settimeout(8)

    def log_message(self, *args):
        pass  # Avoid logging authorization headers or submitted data.

    def reply(self, status, body=b'', mime='application/json', etag=''):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Access-Control-Allow-Origin', '*')
        if etag:
            self.send_header('ETag', '"' + etag + '"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/health':
            return self.reply(200, b'{"service":"metadata-receiver","version":1}')
        if self.path == '/api/v1/check':
            return self.reply(200, b'{"service":"metadata-receiver","authenticated":true}') if self.authorized() else self.reply(401)
        state, image = self.server.store.snapshot()
        if self.path == '/nowplaying.json':
            return self.reply(200, json.dumps(state, ensure_ascii=False).encode())
        if self.path == '/artwork' or self.path.startswith('/artwork/'):
            expected = '/artwork/' + hashlib.sha256(image).hexdigest()
            if self.path != '/artwork' and self.path != expected:
                return self.reply(404)
            if not image:
                return self.reply(204)
            return self.reply(200, image, image_type(image)[1], hashlib.sha256(image).hexdigest())
        self.reply(404)

    def authorized(self):
        return hmac.compare_digest(self.headers.get('Authorization', '').encode(),
                                   ('Bearer ' + self.server.token).encode())

    def write_state(self, heartbeat=False):
        if not self.authorized():
            return self.reply(401)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_BODY or self.headers.get('Transfer-Encoding'):
                return self.reply(413)
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply(415)
            body = self.rfile.read(size)
            if len(body) != size:
                return self.reply(400)
            payload = json.loads(body)
            if heartbeat:
                if not isinstance(payload, dict) or not self.server.store.heartbeat(payload.get('revision')):
                    return self.reply(409)
                return self.reply(200, b'{"ok":true}')
            revision = self.server.store.put(payload)
            self.reply(200, json.dumps({'ok': True, 'revision': revision}).encode())
        except (ValueError, TypeError, KeyError):
            self.reply(400)
        except OSError:
            self.reply(503)

    def do_PUT(self):
        if self.path != '/api/v1/nowplaying':
            return self.reply(404)
        self.write_state()

    def do_POST(self):
        if self.path != '/api/v1/heartbeat':
            return self.reply(404)
        self.write_state(heartbeat=True)


def main():
    parser = argparse.ArgumentParser(description='Receptor autohospedado de MetaDATA')
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--init', action='store_true', help='Crear configuración y clave local')
    parser.add_argument('--host', default='127.0.0.1', help='Dirección inicial, solo con --init')
    parser.add_argument('--directory', default='./receiver-data', help='Carpeta inicial, solo con --init')
    args = parser.parse_args()
    if args.init:
        # Exclusive creation never overwrites an existing publication key.
        args.config.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(host=args.host, port=8090, directory=args.directory,
                                         token=secrets.token_urlsafe(32), ttl=45), indent=2))
        print('Configuración creada. La clave está en ese archivo; no se muestra en registros.')
        return
    config = json.loads(args.config.read_text())
    server = ReceiverServer((config['host'], config['port']), config['directory'], config['token'], config.get('ttl', 45))
    print('Receptor listo. Coloca un proxy HTTPS delante para publicarlo en Internet.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
