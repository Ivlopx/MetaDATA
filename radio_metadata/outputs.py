"""Validated local exports and optional, explicitly configured network outputs."""
from .credentials import read_secret, secret_id

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import xml.etree.ElementTree as Writer

from defusedxml import ElementTree as ET
import httpx

from .config import atomic_write
from .model import clean
from . import __version__


def image_type(data):
    if not data or len(data) > 4 * 1024 * 1024:
        return None
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png', 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'jpg', 'image/jpeg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp', 'image/webp'
    return None


def xml_state(state):
    root = Writer.Element('PLAYER', name='MetaDATA', version=__version__)
    fields = {'CASTTITLE': state['text'] if state['is_music'] else '', 'ARTIST': state['artist'], 'TITLE': state['title'] if state['is_music'] else '',
              'ALBUM': state['album'], 'YEAR': state['year'], 'GENRE': state['genre'],
              'ISRC': state['isrc'], 'SOURCE': state['source'], 'IS_MUSIC': str(state['is_music']).lower(),
              'DURATION_MS': str(state['duration_ms'] or ''), 'ARTWORK': state['artwork_file']}
    Writer.SubElement(root, 'TRACK', fields)
    return Writer.tostring(root, encoding='utf-8', xml_declaration=True)


class LocalOutput:
    def __init__(self, directory: Path):
        self.directory = directory

    def _image(self, data):
        kind = image_type(data)
        if not kind:
            return ''
        name = f'artwork-{hashlib.sha256(data).hexdigest()[:24]}.{kind[0]}'
        path = self.directory / name
        if not path.exists():
            atomic_write(path, data)
        return name

    def publish(self, decision, config):
        track = decision.song
        logo = b''
        if config.logo_path:
            try:
                path = Path(config.logo_path)
                if path.stat().st_size <= 4 * 1024 * 1024:
                    logo = path.read_bytes()
            except OSError:
                pass
        logo_file = self._image(logo)
        song_file = self._image(track.artwork) if track else ''
        state = {
            'schema_version': 3, 'updated_at': datetime.now(timezone.utc).isoformat(),
            'stale_seconds': config.stale_seconds, 'text': clean(decision.text) if track else '',
            'display_message': '' if track else clean(decision.text),
            'source': decision.source, 'is_music': track is not None, 'conflict': decision.conflict,
            'artist': clean(track.artist) if track else '', 'title': clean(track.title) if track else '',
            'album': clean(track.album) if track else '', 'album_artist': clean(track.album_artist) if track else '',
            'year': clean(track.year) if track else '', 'genre': clean(track.genre) if track else '',
            'isrc': clean(track.isrc) if track else '', 'duration_ms': track.duration_ms if track else None,
            'position_ms': track.position_ms if track else None, 'track_number': track.track_number if track else None,
            'artwork_file': (song_file or logo_file) if track else '', 'logo_file': logo_file,
            'artwork_origin': (track.artwork_origin or 'source') if song_file else ('station_logo' if track and logo_file else ''),
            'station': config.station_name, 'slogan': config.slogan, 'description': config.description,
            'website': config.website, 'idle_message': config.idle_message, 'stream_url': config.stream_url,
        }
        # No input filename, credentials, or observed/excluded tracks in public exports.
        atomic_write(self.directory / 'nowplaying.txt', (state['text'] + '\n').encode('utf-8'))
        atomic_write(self.directory / 'nowplaying.xml', xml_state(state))
        atomic_write(self.directory / 'nowplaying.json', json.dumps(state, ensure_ascii=False, indent=2).encode('utf-8'))
        from .player import PLAYER_HTML
        player = self.directory / 'player.html'
        if not player.exists() or player.read_bytes() != PLAYER_HTML.encode('utf-8'):
            atomic_write(player, PLAYER_HTML.encode('utf-8'))
        keep = {state['artwork_file'], logo_file}
        files = sorted(self.directory.glob('artwork-*.*'), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[40:]:
            if old.name not in keep:
                old.unlink(missing_ok=True)
        return state


class RetryingOutput:
    refresh_seconds = 30
    def __init__(self):
        self.last_key = None
        self.next_attempt = 0.0
        self.failures = 0
        self.status = 'Sin enviar'

    def key(self, decision, state):
        return decision.text

    def send(self, decision, state=None):
        key = self.key(decision, state)
        now = time.monotonic()
        if key != self.last_key and not self.failures:
            self.next_attempt = 0
        if now < self.next_attempt:
            return self.status
        try:
            self.status = self.publish(decision, state)
            self.last_key, self.failures, self.next_attempt = key, 0, now + self.refresh_seconds
        except Exception:
            self.failures += 1
            self.next_attempt = now + min(60, 2 ** min(self.failures, 6))
            self.status = self.error_message
        return self.status


class IcecastOutput(RetryingOutput):
    error_message = 'Error Icecast; comprobar conexión/credenciales (reintentando)'

    def __init__(self, target, credentials=None):
        super().__init__()
        self.target = target
        self.credentials = credentials

    def key(self, decision, state):
        return decision.text if decision.song else '', (state or {}).get('artwork_url', '')

    def publish(self, decision, state=None):
        password = read_secret(self.credentials, secret_id('icecast', self.target['url'], self.target['mount'], self.target.get('username', 'source')), self.target.get('password_env', ''), managed=self.target.get('managed_password', False))
        if not password:
            raise ValueError('Falta contraseña Icecast')
        params = {'mount': self.target['mount'], 'mode': 'updinfo', 'song': decision.text if decision.song else '', 'charset': 'UTF-8'}
        if self.target.get('send_artwork_url'):
            # Empty URL deliberately clears the old song artwork during a break.
            params['url'] = (state or {}).get('artwork_url', '') if decision.song else ''
        with httpx.Client(timeout=3, follow_redirects=False, trust_env=False) as client:
            response = client.get(self.target['url'].rstrip('/') + '/admin/metadata', params=params,
                                  auth=(self.target.get('username', 'source'), password))
            response.raise_for_status()
            if len(response.content) > 128000:
                raise ValueError('Respuesta demasiado grande')
            root = ET.fromstring(response.content)
            message = (root.findtext('message') or '').strip().casefold()
            # KH can return 1 even when it says "Mountpoint will not accept this URL update".
            if root.findtext('return') != '1' or message != 'metadata update successful':
                raise ValueError('Respuesta no confirmada de Icecast')
            if self.target.get('verify_url'):
                from .remote import read_json, icecast_state, same_text
                observed = icecast_state(read_json(client, self.target['verify_url']), self.target['mount'])
                if not observed['online'] or not same_text(observed['text'], decision.text if decision.song else ''):
                    raise ValueError('Lectura remota no coincide')
                if self.target.get('send_artwork_url') and observed.get('artwork_url', '') != params['url']:
                    raise ValueError('La URL de carátula remota no coincide')
                return 'Icecast: título y datos enviados verificados por lectura remota'
        return 'Icecast: solicitud aceptada; entrega remota aún sin verificar'


class AzuraCastOutput(RetryingOutput):
    error_message = 'Error de publicación AzuraCast; comprobar permisos y conexión (reintentando)'

    def __init__(self, config, credentials=None):
        super().__init__()
        self.config = config
        self.credentials = credentials

    def publish(self, decision, state=None):
        token = read_secret(self.credentials, secret_id('azuracast', self.config.azuracast_url), self.config.azuracast_key_env, managed=secret_id('azuracast', self.config.azuracast_url) in self.config.managed_credentials)
        if not token:
            raise ValueError('Falta clave API AzuraCast')
        # Restrict to supported, editorial fields; never forward album, art, media_id or liq_*.
        payload = {'artist': clean(decision.song.artist) if decision.song else '',
                   'title': clean(decision.song.title) if decision.song else ''}
        url = f'{self.config.azuracast_url.rstrip("/")}/api/station/{self.config.azuracast_station}/nowplaying/update'
        with httpx.Client(timeout=3, follow_redirects=False, trust_env=False) as client:
            response = client.post(url, data=payload, headers={'X-API-Key': token})
            response.raise_for_status()
            if len(response.content) > 128000 or response.json().get('success') is not True:
                raise ValueError('Respuesta AzuraCast no confirmada')
        return 'AzuraCast: solicitud de artista/título aceptada; comprobar monitor remoto'


class WebDavOutput(RetryingOutput):
    """Upload exact assets to an existing HTTPS WebDAV folder; JSON is committed last."""
    error_message = 'Error de alojamiento; carátula nueva sin publicar (reintentando)'

    def __init__(self, config, directory, credentials=None):
        super().__init__()
        self.config, self.directory = config, directory
        self.credentials = credentials
        self.uploaded_images = set()
        self.artwork_url = ''
        self.player_uploaded = False
        self.refresh_seconds = min(10, config.stale_seconds / 3)

    def key(self, decision, state):
        return decision.text, (state or {}).get('artwork_file'), (state or {}).get('logo_file')

    def send(self, decision, state=None):
        if state is None:
            self.artwork_url = ''
            return 'Alojamiento: esperando exportación local válida'
        # Never expose the URL of an older track when upload is failing/backing off.
        if self.key(decision, state) != self.last_key:
            self.artwork_url = ''
        return super().send(decision, state)

    def publish(self, decision, state):
        password = read_secret(self.credentials, secret_id('webdav', self.config.webdav_upload_url, self.config.webdav_username), self.config.webdav_password_env, managed=secret_id('webdav', self.config.webdav_upload_url, self.config.webdav_username) in self.config.managed_credentials)
        if not password:
            raise ValueError('Falta contraseña WebDAV')
        upload = self.config.webdav_upload_url.rstrip('/')
        public = self.config.webdav_public_url.rstrip('/')
        auth = (self.config.webdav_username, password)
        with httpx.Client(timeout=3, follow_redirects=False, trust_env=False) as client:
            def put(name, data, mime):
                result = client.put(upload + '/' + name, content=data, auth=auth, headers={'Content-Type': mime})
                result.raise_for_status()
            for name in {state['artwork_file'], state['logo_file']} - {''}:
                if name not in self.uploaded_images:
                    data = (self.directory / name).read_bytes()
                    kind = image_type(data)
                    if not kind:
                        raise ValueError('Imagen no válida')
                    put(name, data, kind[1])
                    self.uploaded_images.add(name)
            from .player import PLAYER_HTML
            if not self.player_uploaded:
                put('player.html', PLAYER_HTML.encode('utf-8'), 'text/html; charset=utf-8')
                self.player_uploaded = True
            public_state = dict(state)
            public_state['artwork_url'] = public + '/' + state['artwork_file'] if state['artwork_file'] else ''
            public_state['logo_url'] = public + '/' + state['logo_file'] if state['logo_file'] else ''
            put('nowplaying.txt', (state['text'] + '\n').encode('utf-8'), 'text/plain; charset=utf-8')
            put('nowplaying.json', json.dumps(public_state, ensure_ascii=False).encode('utf-8'), 'application/json')
        self.artwork_url = public_state['artwork_url']
        return 'Alojamiento: JSON e imágenes publicados; reproductor en la URL pública'
