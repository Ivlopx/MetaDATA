from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".radio-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@dataclass
class Config:
    version: int = 4
    ogg_ffmpeg_path: str = ""
    encoder_format: str = "aac"
    encoder_hls_enabled: bool = False
    encoder_radiocaster_variables: bool = False
    encoder_sample_rate: int = 48000
    encoder_channels: int = 2
    encoder_bitrate: int = 128
    history_visible_limit: int = 200
    cover_cache_mb: int = 128
    theme: str = "system"
    managed_credentials: list[str] = field(default_factory=list)
    station_name: str = "Mi estación"
    slogan: str = "Tu música, tu compañía"
    description: str = ""
    website: str = ""
    idle_message: str = "Mi estación • Tu música, tu compañía"
    break_message: str = "Mi estación • En un momento, más música"
    logo_path: str = ""
    poll_seconds: int = 2
    priority: str = "radioboss"
    radioboss_enabled: bool = False
    radioboss_url: str = "http://127.0.0.1:9001/"
    radioboss_user: str = ""
    radioboss_password_env: str = "RADIOBOSS_PASSWORD"
    spotify_enabled: bool = True
    spotify_app_id_contains: str = "spotify"
    spotify_publish: bool = False
    windows_sources: list[dict] = field(default_factory=list)
    source_priority: list[str] = field(default_factory=list)
    music_folders: list[str] = field(default_factory=list)
    excluded_folders: list[str] = field(default_factory=list)
    folder_rules: list[dict] = field(default_factory=list)
    station_genre: str = ""
    title_format: str = "{artist} - {title}"
    audio_monitor_enabled: bool = False
    statistics_enabled: bool = False
    statistics_url: str = ""
    statistics_format: str = "generic"
    statistics_mount: str = "/live.mp3"
    monitor_interval_seconds: int = 60
    monitor_sample_seconds: int = 5
    monitor_silence_seconds: int = 3
    monitor_threshold_db: int = -50
    monitor_confirmations: int = 2
    monitor_retention_days: int = 30
    receiver_enabled: bool = False
    receiver_url: str = ""
    receiver_heartbeat_seconds: int = 10
    excluded_terms: list[str] = field(default_factory=lambda: [
        "anuncio", "publicidad", "commercial", "advertisement", "promo", "jingle", "spot"])
    excluded_types: list[str] = field(default_factory=lambda: [
        "commercial", "advertisement", "promo", "jingle", "advert", "sweep", "voice"])
    # Optional direct Icecast outputs; RadioCaster's file is the recommended route.
    icecast_targets: list[dict] = field(default_factory=list)
    azuracast_url: str = "https://azuracast.example"
    azuracast_station: str = "2"
    remote_monitor_enabled: bool = False
    remote_poll_seconds: int = 10
    icecast_monitor_url: str = "https://icecast.example:8000"
    icecast_monitor_mount: str = "/live.mp3"
    azuracast_write_enabled: bool = False
    azuracast_key_env: str = "AZURACAST_API_KEY"
    stream_url: str = ""
    local_server_enabled: bool = False
    local_server_port: int = 12882
    stale_seconds: int = 30
    webdav_enabled: bool = False
    webdav_upload_url: str = ""
    webdav_public_url: str = ""
    webdav_username: str = ""
    webdav_password_env: str = "METADATA_WEBDAV_PASSWORD"

    def validate(self):
        defaults = Config()
        for key in self.__dataclass_fields__:
            if type(getattr(self, key)) is not type(getattr(defaults, key)):
                raise ValueError(f"Tipo inválido para {key}")
        if not all(isinstance(key, str) and key for key in self.managed_credentials):
            raise ValueError("Referencias de credenciales inválidas")
        if self.version != 4:
            raise ValueError("Versión de configuración no compatible")
        if self.encoder_format not in ('aac', 'mp3', 'ogg'):
            raise ValueError('Formato de codificador inválido')
        if self.encoder_hls_enabled and self.encoder_format != 'aac':
            raise ValueError('La prueba HLS requiere seleccionar AAC.')
        if self.encoder_sample_rate not in (32000, 44100, 48000) or self.encoder_channels not in (1, 2) or not 32 <= self.encoder_bitrate <= 320:
            raise ValueError('Usa 32000, 44100 o 48000 Hz, uno o dos canales y 32–320 kbps.')
        if not 10 <= self.history_visible_limit <= 1000 or not 8 <= self.cover_cache_mb <= 4096:
            raise ValueError("Historial: 10–1000 canciones; caché: 8–4096 MB")
        if self.theme not in ("system", "light", "dark"):
            raise ValueError("Tema inválido")
        if type(self.poll_seconds) is not int or not 1 <= self.poll_seconds <= 30:
            raise ValueError("El intervalo debe estar entre 1 y 30 segundos")
        if self.priority not in ("radioboss", "spotify"):
            raise ValueError("Prioridad inválida")
        from .title_format import validate_format
        validate_format(self.title_format)
        for key, low, high in (('monitor_interval_seconds', 15, 300), ('monitor_sample_seconds', 3, 10),
                               ('monitor_silence_seconds', 1, 10), ('monitor_threshold_db', -90, -10),
                               ('monitor_confirmations', 1, 5), ('monitor_retention_days', 1, 365)):
            if not low <= getattr(self, key) <= high:
                raise ValueError(f'{key}: usa un valor entre {low} y {high}')
        if self.monitor_silence_seconds > self.monitor_sample_seconds:
            raise ValueError('El silencio mínimo no puede superar la duración de la muestra.')
        if self.audio_monitor_enabled and not self.stream_url:
            raise ValueError('Completa el enlace de audio para activar el monitoreo.')
        if self.statistics_format not in ('generic', 'icecast', 'azuracast'):
            raise ValueError('Formato de estadísticas inválido')
        if self.statistics_url:
            self._url(self.statistics_url)
            parsed = urlsplit(self.statistics_url)
            if parsed.scheme != 'https' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
                raise ValueError('La API de estadísticas requiere HTTPS, salvo pruebas locales.')
        if self.statistics_enabled and not self.statistics_url:
            raise ValueError('Completa la dirección de estadísticas.')
        if not self.statistics_mount.startswith('/'):
            raise ValueError('El punto de montaje debe comenzar con /.')
        if not 1 <= self.receiver_heartbeat_seconds <= 10:
            raise ValueError('La confirmación al receptor debe ser cada 1–10 segundos.')
        if self.receiver_url:
            self._url(self.receiver_url)
            url = urlsplit(self.receiver_url)
            if url.scheme != 'https' and url.hostname not in ('127.0.0.1', 'localhost', '::1'):
                raise ValueError('El receptor requiere HTTPS, salvo en pruebas locales.')
        if self.receiver_enabled and not self.receiver_url:
            raise ValueError('Completa la dirección del receptor.')
        if self.receiver_enabled and self.poll_seconds > self.receiver_heartbeat_seconds:
            raise ValueError('La consulta de fuentes debe ser igual o más frecuente que la confirmación al receptor.')
        from .source_catalog import windows_source_id
        source_ids, app_ids = set(), set()
        if len(self.windows_sources) > 32:
            raise ValueError('Se admiten hasta 32 fuentes de Windows.')
        expected = {'id', 'name', 'app_id', 'enabled', 'publish', 'allow_unknown'}
        for source in self.windows_sources:
            if not isinstance(source, dict) or set(source) != expected:
                raise ValueError('Fuente multimedia de Windows inválida')
            if any(not isinstance(source[key], str) or not source[key].strip() or len(source[key]) > 512
                   or any(ord(c) < 32 for c in source[key]) for key in ('id', 'name', 'app_id')):
                raise ValueError('Nombre o identificador multimedia inválido')
            if source['id'] != windows_source_id(source['app_id']):
                raise ValueError('El identificador de la fuente no corresponde a su aplicación')
            if source['id'] in source_ids or source['app_id'].casefold() in app_ids:
                raise ValueError('Hay fuentes multimedia duplicadas')
            if self.spotify_app_id_contains.casefold() in source['app_id'].casefold():
                raise ValueError('Configura Spotify desde su fuente existente.')
            if any(type(source[key]) is not bool for key in ('enabled', 'publish', 'allow_unknown')):
                raise ValueError('Los permisos de una fuente deben ser booleanos')
            source_ids.add(source['id'])
            app_ids.add(source['app_id'].casefold())
        if any(not isinstance(key, str) or key not in source_ids | {'radioboss', 'spotify'} for key in self.source_priority):
            raise ValueError('La prioridad contiene una fuente desconocida')
        if len(set(self.source_priority)) != len(self.source_priority):
            raise ValueError('La prioridad contiene fuentes repetidas')
        if len(self.folder_rules) > 256:
            raise ValueError('Se admiten hasta 256 reglas de carpetas.')
        for rule in self.folder_rules:
            if (not isinstance(rule, dict) or set(rule) != {'path', 'action', 'recursive'}
                    or not isinstance(rule['path'], str) or not rule['path'].strip()
                    or len(rule['path']) > 4096 or rule['action'] not in ('allow', 'block')
                    or type(rule['recursive']) is not bool):
                raise ValueError('Regla de carpeta inválida')
        for key, low, high in (("remote_poll_seconds", 5, 300), ("local_server_port", 1024, 65535), ("stale_seconds", 15, 300)):
            if not low <= getattr(self, key) <= high:
                raise ValueError(f"{key}: valor permitido entre {low} y {high}")
        self._url(self.azuracast_url)
        self._url(self.icecast_monitor_url)
        if self.stream_url:
            self._url(self.stream_url)
        if not self.azuracast_station or not all(c.isalnum() or c in "_-" for c in self.azuracast_station):
            raise ValueError("Identificador de estación inválido")
        if self.azuracast_write_enabled and urlsplit(self.azuracast_url).scheme != "https":
            raise ValueError("La publicación autenticada AzuraCast requiere HTTPS")
        for value in (self.webdav_upload_url, self.webdav_public_url):
            if value:
                self._url(value)
                if urlsplit(value).scheme != "https":
                    raise ValueError("El alojamiento de imágenes requiere HTTPS")
        if self.webdav_enabled and not all((self.webdav_upload_url, self.webdav_public_url)):
            raise ValueError("Completa URL WebDAV y URL pública")
        for key in ("radioboss_password_env", "azuracast_key_env", "webdav_password_env"):
            value = getattr(self, key)
            if value and not all(c.isalnum() or c == "_" for c in value):
                raise ValueError(f"{key}: escribe el nombre de una variable de entorno")
        for key in ("music_folders", "excluded_folders", "excluded_terms", "excluded_types"):
            value = getattr(self, key)
            if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
                raise ValueError(f"{key}: usa una lista de textos no vacíos")
        for key in ("station_name", "idle_message", "break_message"):
            if not getattr(self, key).strip() or any(ord(c) < 32 for c in getattr(self, key)):
                raise ValueError(f"{key}: escribe una sola línea no vacía")
        self._url(self.radioboss_url)
        if not self.spotify_app_id_contains.strip():
            raise ValueError("El identificador de Spotify no puede estar vacío")
        for target in self.icecast_targets:
            if not isinstance(target, dict) or set(target) - {"name", "url", "mount", "username", "password_env", "enabled", "send_artwork_url", "verify_url", "managed_password"}:
                raise ValueError("Destino Icecast inválido")
            for key in ("name", "url", "mount", "username", "password_env", "verify_url"):
                if key in target and not isinstance(target[key], str):
                    raise ValueError(f"Icecast {key} debe ser texto")
            if "managed_password" in target and type(target["managed_password"]) is not bool:
                raise ValueError("managed_password debe ser booleano")
            if "enabled" in target and type(target["enabled"]) is not bool:
                raise ValueError("Icecast enabled debe ser booleano")
            if "send_artwork_url" in target and type(target["send_artwork_url"]) is not bool:
                raise ValueError("send_artwork_url debe ser booleano")
            if target.get("verify_url"):
                self._url(target["verify_url"])
            if target.get("send_artwork_url") and not self.webdav_enabled:
                raise ValueError("Para enviar StreamUrl activa primero el alojamiento de imágenes")
            self._url(target.get("url", ""))
            if not target.get("mount", "").startswith("/"):
                raise ValueError("Icecast requiere un mount que comience por /")
        if self.azuracast_write_enabled and any(t.get("enabled", False) for t in self.icecast_targets):
            raise ValueError("Elige publicación directa Icecast o AzuraCast para evitar escritores simultáneos")

    @staticmethod
    def _url(value):
        url = urlsplit(value)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Usa URL http(s) sin contraseña, parámetros ni fragmento")


class ConfigStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "config.json"

    def load(self):
        if not self.path.exists():
            config = Config()
            self.save(config)
            return config
        original = self.path.read_bytes()
        values = json.loads(original)
        if not isinstance(values, dict):
            raise ValueError("La configuración debe ser un objeto JSON")
        merge_title = 'broadcast_title_format' in values
        if merge_title:
            values['title_format'] = values.pop('broadcast_title_format')
        old_version = values.get("version", 1)
        migrate = old_version in (1, 2, 3)
        if migrate:
            values["version"] = 4
        config = Config(**values)
        config.validate()
        if migrate:
            backup = self.directory / f"config.v{old_version}.backup.json"
            if not backup.exists():
                atomic_write(backup, original)
            self.save(config)
        if merge_title:
            backup = self.directory / 'config.split-title.backup.json'
            if not backup.exists():
                atomic_write(backup, original)
            self.save(config)
        return config

    def save(self, config):
        config.validate()
        atomic_write(self.path, json.dumps(asdict(config), ensure_ascii=False, indent=2).encode("utf-8"))
