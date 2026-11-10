import asyncio
import logging
import re
from dataclasses import replace

from .credentials import WindowsCredentials, MemoryCredentials
from .model import Snapshot, resolve
from .outputs import LocalOutput, WebDavOutput
from .sources import make_sources
from .storage import History

log = logging.getLogger(__name__)


class Engine:
    def __init__(self, config, directory, demo=False, credentials=None):
        self.directory, self.demo = directory, demo
        self.credentials = credentials if credentials is not None else (MemoryCredentials() if demo else WindowsCredentials(directory))
        self.scenario, self.mode = 'radioboss', 'auto'
        self.mode_provider = None
        self.history = History(directory / ('demo-history.sqlite3' if demo else 'history.sqlite3'))
        self.local = LocalOutput(directory / ('demo-output' if demo else 'output'))
        self.last_state = None
        self.server = None
        self.server_error = ''
        self.remote_records = []
        self.configure(config)

    def configure(self, config):
        config.validate()
        self.config = config
        self.cache_history = self.history.recent_artwork_files(config.history_visible_limit)
        # Legacy destination settings must never restart retired direct writers.
        self.outputs = []
        self.webdav = WebDavOutput(config, self.local.directory, self.credentials) if config.webdav_enabled and not self.demo else None
        self.monitor = None
        self.remote_records = []
        if self.server:
            self.server.close()
            self.server = None
        self.server_error = ''
        if config.local_server_enabled:
            try:
                from .webserver import LocalServer
                self.server = LocalServer(self.local.directory, config.local_server_port)
            except OSError:
                self.server_error = 'No se pudo abrir la vista local; revisa si el puerto está ocupado'

    async def publish(self, decision):
        statuses, state = [], None
        try:
            state = await asyncio.to_thread(self.local.publish, decision, self.config, self.cache_history)
        except Exception as error:
            log.error('Salida local: %s', type(error).__name__)
            statuses.append('Error de salida local: el emisor podría conservar el título anterior')
        if self.webdav:
            statuses.append(await asyncio.to_thread(self.webdav.send, decision, state))
        if state is not None:
            state['artwork_url'] = self.webdav.artwork_url if self.webdav else ''
        if self.server:
            statuses.append('Vista y API local: ' + self.server.url)
        if self.server_error:
            statuses.append(self.server_error)
        return statuses

    async def tick(self):
        async def poll(source):
            try:
                return await asyncio.wait_for(source.poll(), timeout=12)
            except Exception as error:
                log.warning('Fuente %s: %s', source.name, type(error).__name__)
                if isinstance(error, ModuleNotFoundError) and re.fullmatch(r'winrt(?:\.[A-Za-z_][A-Za-z_0-9]*)*', error.name or ''):
                    return Snapshot(source.name, error=f'Falta el componente {error.name}. Cierra la app y vuelve a ejecutar instalar.bat.')
                return Snapshot(source.name, error=f'No disponible ({type(error).__name__}); comprobar ajustes')
        mode = self.mode_provider() if self.mode_provider else self.mode
        sources = [] if mode == 'station' else make_sources(self.config, self.demo, self.scenario, credentials=self.credentials)
        snapshots = await asyncio.gather(*(poll(s) for s in sources))
        effective = replace(self.config, music_folders=[r'C:\Musica'], spotify_publish=True) if self.demo else self.config
        # Honor an operator override that arrived while a source request was in flight.
        mode = self.mode_provider() if self.mode_provider else self.mode
        decision = resolve(snapshots, effective, mode)
        errors = []
        try:
            self.history.record(decision)
            self.cache_history = self.history.recent_artwork_files(self.config.history_visible_limit)
        except Exception as error:
            log.error('Historial: %s', type(error).__name__)
            errors.append('No se pudo guardar el historial')
        statuses = await self.publish(decision)
        if self.last_state != (decision.source, decision.reason, decision.conflict):
            log.info('Selección: %s; %s; conflicto=%s', decision.source, decision.reason, decision.conflict)
            self.last_state = decision.source, decision.reason, decision.conflict
        try:
            rows = self.history.recent(self.config.history_visible_limit)
        except Exception:
            rows = []
        return decision, snapshots, errors + statuses, rows

    def close(self):
        if self.server:
            self.server.close()
            self.server = None
        self.history.close()
