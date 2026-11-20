"""Report changes in music and commercial breaks to TuneIn AIR."""

import logging
import time

import httpx

from .credentials import CredentialError, secret_id
from .model import clean

log = logging.getLogger(__name__)
AIR_ENDPOINT = 'https://air.radiotime.com/Playing.ashx'


def tunein_key(config):
    return secret_id('tunein', config.tunein_station_id, config.tunein_partner_id)


class TuneInOutput:
    def __init__(self, config, credentials):
        self.config = config
        self.credentials = credentials
        self.key = tunein_key(config)
        self.last_sent = None
        self.next_attempt = 0
        self.failures = 0
        self.status = 'TuneIn AIR: sin enviar'

    def send(self, decision):
        track = decision.song
        # Late album data or reading the same title again should not cause another request.
        event = (clean(track.artist), clean(track.title)) if track else ()
        now = time.monotonic()
        if event == self.last_sent or now < self.next_attempt:
            return self.status

        try:
            partner_key = self.credentials.get(self.key)
        except CredentialError:
            partner_key = ''
        if not partner_key:
            self.status = 'TuneIn AIR: revisa la clave guardada'
            self.next_attempt = now + 30
            return self.status

        params = {'id': self.config.tunein_station_id,
                  'partnerId': self.config.tunein_partner_id, 'partnerKey': partner_key}
        if track:
            params.update(artist=event[0], title=event[1])
            if self.config.tunein_include_album and (album := clean(track.album)):
                params['album'] = album
        else:
            params['commercial'] = 'true'

        try:
            with httpx.Client(timeout=4, follow_redirects=False, trust_env=False) as client:
                with client.stream('GET', AIR_ENDPOINT, params=params) as response:
                    status_code = response.status_code
        except httpx.HTTPError:
            status_code = None

        if status_code == 200:
            self.last_sent = event
            self.failures = 0
            self.next_attempt = 0
            self.status = 'TuneIn AIR: canción aceptada' if track else 'TuneIn AIR: pausa aceptada'
            log.info(self.status)
        else:
            # A timeout can leave the remote state unknown even if the request was applied.
            self.last_sent = None
            self.failures += 1
            self.next_attempt = time.monotonic() + min(300, 30 * 2 ** min(self.failures - 1, 4))
            detail = f'HTTP {status_code}' if status_code is not None else 'fallo de conexión'
            self.status = f'TuneIn AIR: {detail}. Se reintentará el estado actual.'
            log.warning(self.status)
        return self.status
