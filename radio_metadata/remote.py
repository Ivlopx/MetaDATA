"""Read-only station observations. Never feed remote titles back into source selection."""
import time
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from .model import clean


def read_json(client, url):
    with client.stream('GET', url) as response:
        response.raise_for_status()
        raw = bytearray()
        for part in response.iter_bytes():
            raw.extend(part)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError('Respuesta de monitor demasiado grande')
        import json
        return json.loads(raw)


def same_text(a, b):
    def normalize(text):
        return unicodedata.normalize('NFC', clean(text)).casefold()
    return normalize(a) == normalize(b)


def safe_image_url(value):
    if not isinstance(value, str):
        return ''
    url = urlsplit(value)
    return value if url.scheme == 'https' and url.hostname and not url.username and not url.password else ''


def azuracast_state(data):
    if not isinstance(data, dict) or 'is_online' not in data:
        raise ValueError('Respuesta AzuraCast incompleta')
    song = (data.get('now_playing') or {}).get('song') or {}
    station = data.get('station') or {}
    return {'service': 'AzuraCast', 'online': data['is_online'] is True,
            'text': clean(song.get('text') or ''), 'artist': clean(song.get('artist') or ''),
            'title': clean(song.get('title') or ''), 'album': clean(song.get('album') or ''),
            'artwork_url': safe_image_url(song.get('art') or ''),
            'listeners': (data.get('listeners') or {}).get('current'),
            'is_live': (data.get('live') or {}).get('is_live') is True,
            'name': clean(station.get('name') or '')}


def icecast_state(data, mount):
    sources = (data.get('icestats') or {}).get('source') or []
    if isinstance(sources, dict):
        sources = [sources]
    def matches_mount(source):
        path = urlsplit(source.get('listenurl', '')).path
        # AzuraCast can advertise /listen/<station>/<mount> through its reverse proxy.
        return path == mount or source.get('mount') == mount or (path.startswith('/listen/') and path.endswith(mount))
    selected = next((s for s in sources if matches_mount(s)), None)
    if selected is None:
        return {'service': 'Icecast', 'online': False, 'text': '', 'artwork_url': ''}
    title, artist = selected.get('title') or '', selected.get('artist') or ''
    text = f'{artist} - {title}' if artist and title else title
    return {'service': 'Icecast', 'online': True, 'text': clean(text),
            'artwork_url': safe_image_url(selected.get('metadata_url') or ''),
            'listeners': selected.get('listeners'), 'format': selected.get('server_type', ''),
            'bitrate': selected.get('bitrate'), 'name': clean(selected.get('server_name') or '')}


class RemoteMonitor:
    def __init__(self, config):
        self.config = config
        self.next_poll = 0
        self.records = []

    def poll(self, expected, force=False):
        now = time.monotonic()
        if force or now >= self.next_poll:
            self.records = []
            with httpx.Client(timeout=3, follow_redirects=False, trust_env=False) as client:
                services = [
                    ('AzuraCast', f'{self.config.azuracast_url.rstrip("/")}/api/nowplaying/{self.config.azuracast_station}', azuracast_state),
                    ('Icecast', self.config.icecast_monitor_url.rstrip('/') + '/status-json.xsl',
                     lambda data: icecast_state(data, self.config.icecast_monitor_mount)),
                ]
                for service, url, parser in services:
                    try:
                        record = parser(read_json(client, url))
                        record['checked_at'] = datetime.now(timezone.utc).isoformat()
                        record['error'] = ''
                    except Exception as error:
                        record = {'service': service, 'online': False, 'error': type(error).__name__,
                                  'text': '', 'artwork_url': '', 'checked_at': datetime.now(timezone.utc).isoformat()}
                    self.records.append(record)
            self.next_poll = now + self.config.remote_poll_seconds
        return [dict(record, matches=bool(record['online'] and not record['error'] and same_text(record['text'], expected)))
                for record in self.records]
