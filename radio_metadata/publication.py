"""Provider-independent publication. Latest state is sent; no historical queue."""
import base64
import json
import time

import httpx

from .credentials import secret_id
from .image_cache import image_type
from .receiver import normalize


def publication_key(config):
    return secret_id('receiver', config.receiver_url.rstrip('/'))


class ReceiverOutput:
    def __init__(self, config, directory, credentials):
        self.config, self.directory, self.credentials = config, directory, credentials
        self.last_key, self.revision = None, ''
        self.next_attempt, self.failures = 0., 0
        self.status = 'Receptor: sin enviar'

    def send(self, decision, state):
        if state is None:
            return 'Error de publicación: esperando salida local válida'
        music = normalize(state)
        # Elapsed position is advisory; it must not trigger an image upload every poll.
        key = json.dumps({k: v for k, v in music.items() if k != 'position_ms'}, sort_keys=True) + state.get('artwork_file', '')
        now = time.monotonic()
        changed = key != self.last_key
        if now < self.next_attempt and (not changed or self.failures):
            return self.status
        try:
            token = self.credentials.get(publication_key(self.config))
            if not token:
                raise ValueError('Missing publication key')
            headers = {'Authorization': 'Bearer ' + token}
            with httpx.Client(timeout=4, follow_redirects=False, trust_env=False, headers=headers) as client:
                base = self.config.receiver_url.rstrip('/')
                if not changed and self.revision:
                    response = client.post(base + '/api/v1/heartbeat', json={'revision': self.revision})
                    if response.status_code == 409:
                        self.last_key, self.revision = None, ''
                        self.next_attempt = 0
                        return 'Receptor: estado perdido; se reenviará la ficha actual'
                else:
                    image = b''
                    name = state.get('artwork_file', '') if state['is_music'] else ''
                    if name:
                        path = (self.directory / name).resolve()
                        if path.parent != (self.directory / 'covers').resolve():
                            raise ValueError('Invalid cover path')
                        if path.stat().st_size > 4 * 1024 * 1024:
                            raise ValueError('Cover too large')
                        image = path.read_bytes()
                        if not image_type(image):
                            raise ValueError('Invalid cover')
                    response = client.put(base + '/api/v1/nowplaying', json={
                        'state': music, 'artwork_base64': base64.b64encode(image).decode('ascii')})
                response.raise_for_status()
                if len(response.content) > 4096:
                    raise ValueError('Oversized response')
                answer = response.json()
                if answer.get('ok') is not True:
                    raise ValueError('Not confirmed')
                self.revision = answer.get('revision', self.revision)
                if not self.revision:
                    raise ValueError('No revision')
            self.last_key = key
            self.failures = 0
            self.next_attempt = now + self.config.receiver_heartbeat_seconds
            self.status = 'Receptor: ficha actual confirmada' if state['is_music'] else 'Receptor: campos de canción vacíos confirmados'
        except Exception:
            self.failures += 1
            self.next_attempt = now + min(30, 2 ** min(self.failures, 5))
            self.status = 'Error de publicación: revisa receptor y clave; reintentando el estado actual'
        return self.status
