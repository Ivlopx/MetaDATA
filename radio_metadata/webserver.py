"""Loopback-only read-only service; never exposes config, history or arbitrary disk paths."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
from urllib.parse import urlsplit

from .outputs import image_type, xml_state
from .player import PLAYER_HTML


def live_state(directory, now=None):
    state = json.loads((directory / 'nowplaying.json').read_text(encoding='utf-8'))
    now = now or datetime.now(timezone.utc)
    age = (now - datetime.fromisoformat(state['updated_at'])).total_seconds()
    if age > state['stale_seconds'] or age < -60:
        state.update(text='', display_text='', display_message=state['idle_message'], source='estación', is_music=False, artist='', title='',
                     album='', album_artist='', year='', genre='', isrc='', duration_ms=None,
                     position_ms=None, track_number=None, artwork_file='',
                     artwork_origin='', stale=True)
    else:
        state['stale'] = False
    return state


class LocalServer:
    def __init__(self, directory, port):
        self.directory = directory
        directory = directory
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
                    self.send_error(403)
                    return
                path = urlsplit(self.path).path
                mime, data = '', None
                try:
                    if path in ('/', '/player.html'):
                        mime, data = 'text/html; charset=utf-8', PLAYER_HTML.encode('utf-8')
                    elif path in ('/nowplaying.json', '/nowplaying.txt', '/nowplaying.xml'):
                        state = live_state(directory)
                        if path.endswith('.json'):
                            mime, data = 'application/json; charset=utf-8', json.dumps(state, ensure_ascii=False).encode('utf-8')
                        elif path.endswith('.txt'):
                            mime, data = 'text/plain; charset=utf-8', (state['text'] + '\n').encode('utf-8')
                        else:
                            mime, data = 'application/xml; charset=utf-8', xml_state(state)
                    elif re.fullmatch(r'/hls/(?:live\.m3u8|segment-[a-f0-9]{16}-[0-9]{8}\.aac)', path):
                        asset = directory / path[1:]
                        if not asset.is_symlink() and not asset.parent.is_symlink():
                            data = asset.read_bytes()
                            mime = 'application/vnd.apple.mpegurl' if path.endswith('.m3u8') else 'audio/aac'
                    elif re.fullmatch(r'/(?:covers/)?artwork-[a-f0-9]{24}\.(png|jpg|webp)', path):
                        asset = directory / path[1:]
                        if not asset.exists() and '/' not in path[1:]:
                            asset = directory / 'covers' / path[1:]
                        data = asset.read_bytes()
                        kind = image_type(data)
                        if kind:
                            mime = kind[1]
                        else:
                            data = None
                except (OSError, ValueError, KeyError, TypeError):
                    self.send_error(503, 'Informacion no disponible')
                    return
                if data is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store' if not mime.startswith('image/') else 'public, max-age=86400')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.end_headers()
                self.wfile.write(data)
        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_port}/player.html'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
