"""Read-only probes, independent of song selection and broadcast outputs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import sqlite3
import struct
import subprocess
import time

import httpx

from .credentials import secret_id
from .remote import read_json, icecast_state, azuracast_state


def stats_key(config):
    return secret_id('statistics', config.statistics_url)


def pcm_levels(pcm, rate=8000, threshold=-50, channels=1):
    if len(pcm) % 2:
        pcm = pcm[:-1]
    samples = [n[0] for n in struct.iter_unpack('<h', pcm)]
    if not samples:
        raise ValueError('No audio samples')
    def db(values):
        mean = sum(v * v for v in values) / len(values)
        return 10 * math.log10(mean / (32768 ** 2)) if mean else -120.
    block = max(1, rate // 10) * channels
    longest = run = 0.
    for start in range(0, len(samples), block):
        part = samples[start:start + block]
        run = run + len(part) / (rate * channels) if db(part) <= threshold else 0.
        longest = max(longest, run)
    return round(db(samples), 1), round(longest, 3), len(samples) / (rate * channels)


def probe_audio(config):
    from .ogg_encoder import find_ffmpeg
    ffmpeg = find_ffmpeg(config.ogg_ffmpeg_path)
    if not ffmpeg:
        return dict(channel='audio', state='error', message='Selecciona FFmpeg en Codificador para analizar el audio.')
    args = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-rw_timeout', '5000000',
            '-protocol_whitelist', 'http,https,tcp,tls,crypto', '-i', config.stream_url,
            '-map', '0:a:0', '-vn', '-t', str(config.monitor_sample_seconds),
            '-ac', '2', '-ar', '8000', '-f', 's16le', 'pipe:1']
    try:
        result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=config.monitor_sample_seconds + 8,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        rms, silence, duration = pcm_levels(result.stdout, threshold=config.monitor_threshold_db, channels=2)
        if result.returncode or duration < config.monitor_sample_seconds * .8:
            raise ValueError('Incomplete audio')
        silent = silence >= config.monitor_silence_seconds
        return dict(channel='audio', state='silence' if silent else 'ok', rms_db=rms,
                    silence_seconds=silence, message='Silencio detectado en la muestra' if silent else 'Audio recibido y decodificado')
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return dict(channel='audio', state='error', message='No se pudo recibir una muestra completa de audio; revisa enlace y formato.')


def probe_statistics(config, credentials):
    try:
        token = credentials.get(stats_key(config))
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        with httpx.Client(timeout=4, follow_redirects=False, trust_env=False, headers=headers) as client:
            data = read_json(client, config.statistics_url)
        if config.statistics_format == 'icecast':
            data = icecast_state(data, config.statistics_mount)
            if not data['online']:
                raise ValueError('Mount offline')
        elif config.statistics_format == 'azuracast':
            data = azuracast_state(data)
            if not data['online']:
                raise ValueError('Station offline')
        count = data.get('listeners')
        if isinstance(count, str) and count.isascii() and count.isdigit():
            count = int(count)
        if type(count) is not int or not 0 <= count <= 10**9 or data.get('online') is False:
            raise ValueError('Missing listener count')
        return dict(channel='statistics', state='ok', listeners=count, message='Oyentes comunicados por el servidor de audio')
    except Exception:
        return dict(channel='statistics', state='error', listeners=None,
                    message='No se pudieron consultar los oyentes; revisa API, formato y permisos.')


class MonitorHistory:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS monitor_samples (
            id INTEGER PRIMARY KEY, checked_at TEXT NOT NULL, channel TEXT NOT NULL,
            state TEXT NOT NULL, listeners INTEGER, rms_db REAL, silence_seconds REAL, scope TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS monitor_incidents (
            id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT,
            channel TEXT NOT NULL, state TEXT NOT NULL, message TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS monitor_time ON monitor_samples(checked_at);
          CREATE TABLE IF NOT EXISTS monitor_scopes (channel TEXT PRIMARY KEY, fingerprint TEXT NOT NULL);
        ''')
        self.last = {}
        self.streak = {}
        self.scopes = {}
        if 'scope' not in {row[1] for row in self.db.execute('PRAGMA table_info(monitor_samples)')}:
            self.db.execute("ALTER TABLE monitor_samples ADD COLUMN scope TEXT NOT NULL DEFAULT ''")
            self.db.commit()

    def configure_scope(self, config):
        stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        for channel, identity in (
            ('audio', (config.audio_monitor_enabled, config.stream_url, config.monitor_threshold_db, config.monitor_silence_seconds)),
            ('statistics', (config.statistics_enabled, config.statistics_url, config.statistics_format, config.statistics_mount))):
            fingerprint = hashlib.sha256(repr(identity).encode()).hexdigest()
            previous = self.db.execute('SELECT fingerprint FROM monitor_scopes WHERE channel=?', (channel,)).fetchone()
            if previous and previous[0] != fingerprint:
                self.db.execute("UPDATE monitor_incidents SET ended_at=?, message=message || ' · comprobación detenida o configuración cambiada' WHERE channel=? AND ended_at IS NULL", (stamp, channel))
                self.last.pop(channel, None)
                self.streak.pop(channel, None)
            self.db.execute('INSERT OR REPLACE INTO monitor_scopes VALUES(?,?)', (channel, fingerprint))
            # Do not mix audience measurements from different endpoints/mounts.
            self.scopes[channel] = hashlib.sha256(repr(identity[1:]).encode()).hexdigest()
        self.db.commit()

    def record(self, rows, config):
        stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        for row in rows:
            channel, state = row['channel'], row['state']
            self.db.execute('INSERT INTO monitor_samples(checked_at,channel,state,listeners,rms_db,silence_seconds,scope) VALUES(?,?,?,?,?,?,?)',
                            (stamp, channel, state, row.get('listeners'), row.get('rms_db'), row.get('silence_seconds'), self.scopes.get(channel, '')))
            key = channel, state
            self.streak[channel] = self.streak.get(channel, 0) + 1 if self.last.get(channel) == key else 1
            self.last[channel] = key
            if self.streak[channel] < config.monitor_confirmations:
                continue
            opened = self.db.execute('SELECT id,state FROM monitor_incidents WHERE channel=? AND ended_at IS NULL', (channel,)).fetchall()
            if state == 'ok' or any(old_state != state for _, old_state in opened):
                self.db.execute('UPDATE monitor_incidents SET ended_at=? WHERE channel=? AND ended_at IS NULL', (stamp, channel))
            if state != 'ok' and not any(old_state == state for _, old_state in opened):
                self.db.execute('INSERT INTO monitor_incidents(started_at,channel,state,message) VALUES(?,?,?,?)', (stamp, channel, state, row['message']))
        cutoff = datetime.fromtimestamp(time.time() - config.monitor_retention_days * 86400, timezone.utc).isoformat(timespec='seconds')
        self.db.execute('DELETE FROM monitor_samples WHERE checked_at < ?', (cutoff,))
        self.db.execute('DELETE FROM monitor_incidents WHERE ended_at IS NOT NULL AND ended_at < ?', (cutoff,))
        # Absolute caps also bound storage at very short intervals.
        self.db.execute('DELETE FROM monitor_samples WHERE id NOT IN (SELECT id FROM monitor_samples ORDER BY id DESC LIMIT 100000)')
        self.db.execute('DELETE FROM monitor_incidents WHERE id NOT IN (SELECT id FROM monitor_incidents ORDER BY id DESC LIMIT 10000)')
        self.db.commit()

    def view(self):
        incidents = self.db.execute('SELECT started_at,ended_at,channel,state,message FROM monitor_incidents ORDER BY id DESC LIMIT 200').fetchall()
        scope = self.scopes.get('statistics', '')
        samples = self.db.execute('SELECT checked_at,listeners FROM monitor_samples WHERE channel="statistics" AND state="ok" AND scope=? ORDER BY id DESC LIMIT 20', (scope,)).fetchall()
        since = datetime.fromtimestamp(time.time() - 86400, timezone.utc).isoformat(timespec='seconds')
        summary = self.db.execute('SELECT COUNT(*),MAX(listeners),AVG(listeners) FROM monitor_samples WHERE channel="statistics" AND state="ok" AND checked_at>=? AND scope=?', (since, scope)).fetchone()
        return dict(incidents=incidents, samples=samples, summary=summary)

    def close(self):
        self.db.close()


class BroadcastMonitor:
    """Probes run off the metadata worker; results never choose a music source."""
    def __init__(self, config, credentials):
        self.config, self.credentials = config, credentials
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='broadcast-monitor')
        self.jobs = {}
        self.next_check = 0
        self.records = {}

    def poll(self, force=False):
        completed = []
        for channel, future in list(self.jobs.items()):
            if future.done():
                try:
                    result = future.result()
                except Exception:
                    result = dict(channel=channel, state='error', message='No se pudo completar la comprobación.')
                result['checked_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
                self.records[channel] = result
                completed.append(result)
                del self.jobs[channel]
        if force or time.monotonic() >= self.next_check:
            for channel, enabled, function, args in (
                ('audio', self.config.audio_monitor_enabled, probe_audio, (self.config,)),
                ('statistics', self.config.statistics_enabled, probe_statistics, (self.config, self.credentials))):
                if enabled and channel not in self.jobs:
                    self.jobs[channel] = self.pool.submit(function, *args)
            self.next_check = time.monotonic() + self.config.monitor_interval_seconds
        return list(self.records.values()), completed

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)
