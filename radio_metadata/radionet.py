"""Publish music and breaks to the radio.net Meta Data Push API."""

import httpx

from .credentials import CredentialError, secret_id
from .model import clean

ENDPOINT = 'https://api.radio.de/info/v2/pushmetadata/playingsong'


class RadioNetOutput:
    def __init__(self, slug, credentials):
        self.slug = slug
        self.credentials = credentials
        self.last_event = None
        self.status = 'radio.net: sin enviar'

    def send(self, decision):
        track = decision.song
        event = (clean(track.artist), clean(track.title)) if track else ()
        if event == self.last_event:
            return self.status

        try:
            key = self.credentials.get(secret_id('radionet', self.slug)).strip()
        except CredentialError:
            key = ''
        if not key:
            self.status = 'radio.net: revisa la clave guardada'
            return self.status

        params = {'broadcast': self.slug, 'apikey': key}
        if track:
            params.update(artist=event[0], title=event[1])
            if album := clean(track.album):
                params['album'] = album
        else:
            params['commercial'] = 'true'

        # The API requests one submission per transition, including when a reply is lost.
        self.last_event = event
        try:
            with httpx.Client(timeout=4, follow_redirects=False, trust_env=False) as client:
                response = client.get(ENDPOINT, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            self.status = f'radio.net: HTTP {error.response.status_code}'
            return self.status
        except httpx.HTTPError:
            self.status = 'radio.net: fallo de conexión'
            return self.status

        try:
            result = response.json()
        except ValueError:
            result = None
        code = result.get('errorCode') if isinstance(result, dict) else None
        if type(code) in (int, str) and str(code) == '0':
            self.status = 'radio.net: canción aceptada' if track else 'radio.net: pausa aceptada'
        else:
            self.status = 'radio.net: el servidor rechazó el envío' if code is not None else 'radio.net: respuesta sin confirmación'
        return self.status
