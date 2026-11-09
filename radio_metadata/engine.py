import asyncio
import logging
import re
from dataclasses import replace

from .model import Snapshot, resolve
from .outputs import AzuraCastOutput, IcecastOutput, LocalOutput, WebDavOutput
from .remote import RemoteMonitor
from .sources import make_sources
from .storage import History

log = logging.getLogger(__name__)


class Engine:
    def __init__(self, config, directory, demo=False):
        self.directory, self.demo = directory, demo
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
        self.outputs = [] if self.demo else [IcecastOutput(t) for t in config.icecast_targets if t.get('enabled', False)]
        if config.azuracast_write_enabled and not self.demo:
            self.outputs.append(AzuraCastOutput(config))
        self.webdav = WebDavOutput(config, self.local.directory) if config.webdav_enabled and not self.demo else None
        self.monitor = RemoteMonitor(config) if config.remote_monitor_enabled and not self.demo else None
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
            state = await asyncio.to_thread(self.local.publish, decision, self.config)
        except Exception as error:
            log.error('Salida local: %s', type(error).__name__)
            statuses.append('Error de salida local: RadioCaster podría conservar el título anterior')
        if self.webdav:
            statuses.append(await asyncio.to_thread(self.webdav.send, decision, state))
        if state is not None:
            state['artwork_url'] = self.webdav.artwork_url if self.webdav else ''
        # Icecast with StreamUrl must still clear old metadata on breaks when hosting is down.
        statuses.extend(await asyncio.gather(*(asyncio.to_thread(o.send, decision, state) for o in self.outputs)))
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
        sources = [] if mode == 'station' else make_sources(self.config, self.demo, self.scenario)
        snapshots = await asyncio.gather(*(poll(s) for s in sources))
        effective = replace(self.config, music_folders=[r'C:\Musica'], spotify_publish=True) if self.demo else self.config
        # Honor an operator override that arrived while a source request was in flight.
        mode = self.mode_provider() if self.mode_provider else self.mode
        decision = resolve(snapshots, effective, mode)
        errors = []
        try:
            self.history.record(decision)
        except Exception as error:
            log.error('Historial: %s', type(error).__name__)
            errors.append('No se pudo guardar el historial')
        statuses = await self.publish(decision)
        if self.monitor:
            self.remote_records = await asyncio.to_thread(self.monitor.poll, decision.text)
        if self.last_state != (decision.source, decision.reason, decision.conflict):
            log.info('Selección: %s; %s; conflicto=%s', decision.source, decision.reason, decision.conflict)
            self.last_state = decision.source, decision.reason, decision.conflict
        try:
            rows = self.history.recent()
        except Exception:
            rows = []
        return decision, snapshots, errors + statuses, rows

    def close(self):
        if self.server:
            self.server.close()
            self.server = None
        self.history.close()
