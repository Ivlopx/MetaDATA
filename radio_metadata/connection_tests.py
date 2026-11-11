"""User-triggered, read-only checks. Never publishes titles or uploads files."""
import asyncio
from pathlib import Path

import httpx

from .credentials import read_secret, secret_id
from .remote import read_json, azuracast_state, icecast_state
from .sources import RadioBossSource, SpotifyWindowsSource


class OverlayCredentials:
    def __init__(self, base, changes):
        self.base, self.changes = base, changes

    def get(self, key):
        return self.changes[key] if key in self.changes else self.base.get(key)


async def check_connection(name, config, credentials, directory):
    try:
        if name == 'Receptor':
            from .publication import publication_key
            def check_receiver():
                token = credentials.get(publication_key(config))
                if not config.receiver_url or not token:
                    return False, 'Completa la dirección y la clave de publicación.'
                with httpx.Client(timeout=4, follow_redirects=False, trust_env=False) as client:
                    response = client.get(config.receiver_url.rstrip('/') + '/api/v1/check', headers={'Authorization': 'Bearer ' + token})
                    response.raise_for_status()
                    if len(response.content) > 4096 or response.json() != {'service': 'metadata-receiver', 'authenticated': True}:
                        return False, 'La dirección respondió, pero no confirmó un receptor de MetaDATA.'
                return True, 'El receptor reconoce la clave. No se publicaron datos en esta prueba.'
            return await asyncio.to_thread(check_receiver)
        if name in ('Codificador Ogg', 'Codificador'):
            from .ogg_encoder import check_ffmpeg, EncoderError
            try:
                if name == 'Codificador Ogg' or config.encoder_format == 'ogg':
                    await asyncio.to_thread(check_ffmpeg, config.ogg_ffmpeg_path)
                    codec = 'libopus'
                else:
                    from .aac_encoder import check_ffmpeg as check_audio
                    await asyncio.to_thread(check_audio, config.ogg_ffmpeg_path, config.encoder_format)
                    codec = config.encoder_format.upper()
                return True, f'FFmpeg incluye {codec}. Esta comprobación no abre RadioCaster ni emite audio.'
            except EncoderError as error:
                return False, str(error)
        if name == 'RadioBOSS':
            source = RadioBossSource(config, credentials)
            result = await asyncio.wait_for(source.poll(), 12)
            if result.error:
                return False, result.error
            return True, 'RadioBOSS respondió. ' + ('Reproducción detectada.' if result.playing else 'Sin reproducción en este momento.')
        if name == 'Spotify':
            result = await asyncio.wait_for(SpotifyWindowsSource(config).poll(), 12)
            if result.error:
                return False, result.error
            return True, 'Windows respondió. ' + ('Sesión Spotify reproduciendo.' if result.playing else 'Abre Spotify y reproduce una canción para comprobar sus datos.')
        if name in ('Now Playing', 'RadioCaster'):
            path = Path(directory) / 'output' / 'nowplaying.xml'
            if not path.is_file():
                return False, 'Todavía no existe el archivo de títulos. Inicia el modo real para generarlo.'
            from defusedxml import ElementTree as ET
            track = ET.fromstring(path.read_bytes()).find('TRACK')
            if track is None or 'CASTTITLE' not in track.attrib:
                return False, 'El XML todavía no tiene el campo CASTTITLE. Espera a la siguiente actualización.'
            return True, 'El XML y su campo CASTTITLE están disponibles. Comprueba que tu emisor lea el archivo y formato seleccionados.'
        if name == 'AzuraCast':
            def check():
                headers = {}
                if config.azuracast_write_enabled:
                    key = secret_id('azuracast', config.azuracast_url)
                    token = read_secret(credentials, key, config.azuracast_key_env, managed=key in config.managed_credentials)
                    if not token:
                        return False, 'Introduce una clave API antes de activar la publicación directa.'
                    headers['X-API-Key'] = token
                    url = f'{config.azuracast_url.rstrip("/")}/api/station/{config.azuracast_station}/profile'
                else:
                    url = f'{config.azuracast_url.rstrip("/")}/api/nowplaying/{config.azuracast_station}'
                with httpx.Client(timeout=3, follow_redirects=False, trust_env=False, headers=headers) as client:
                    data = read_json(client, url)
                if config.azuracast_write_enabled:
                    return True, 'La clave permite consultar la estación. Esta prueba no publica títulos ni confirma permisos de escritura.'
                state = azuracast_state(data)
                return True, 'AzuraCast respondió. ' + ('Estación online.' if state['online'] else 'Estación fuera de línea.')
            return await asyncio.wait_for(asyncio.to_thread(check), 8)
        if name == 'Alojamiento de carátulas':
            def check():
                password = read_secret(credentials, secret_id('webdav', config.webdav_upload_url, config.webdav_username), config.webdav_password_env, managed=secret_id('webdav', config.webdav_upload_url, config.webdav_username) in config.managed_credentials)
                if not config.webdav_upload_url or not password:
                    return False, 'Completa el alojamiento, usuario y contraseña.'
                with httpx.Client(timeout=3, follow_redirects=False, trust_env=False) as client:
                    result = client.request('PROPFIND', config.webdav_upload_url, headers={'Depth': '0'}, auth=(config.webdav_username, password))
                    result.raise_for_status()
                return True, 'El alojamiento permite consultar la carpeta. No se subieron archivos ni se verificó escritura.'
            return await asyncio.wait_for(asyncio.to_thread(check), 8)
        if name == 'Icecast directo':
            def check():
                target = config.icecast_targets[0]
                url = target.get('verify_url') or target['url'].rstrip('/') + '/status-json.xsl'
                with httpx.Client(timeout=3, follow_redirects=False, trust_env=False) as client:
                    state = icecast_state(read_json(client, url), target['mount'])
                if not state['online']:
                    return False, 'Las estadísticas respondieron, pero ese mount no aparece online.'
                return True, 'El mount aparece online. Esta consulta pública no verifica contraseña ni permiso para publicar títulos.'
            return await asyncio.wait_for(asyncio.to_thread(check), 8)
        return False, 'Servicio no disponible en esta aplicación.'
    except ModuleNotFoundError:
        return False, 'Falta un componente de Windows. Vuelve a ejecutar el instalador y reinicia la app.'
    except Exception:
        return False, 'No se pudo completar la prueba. Revisa dirección, credenciales y permisos. No se modificó la emisión.'
