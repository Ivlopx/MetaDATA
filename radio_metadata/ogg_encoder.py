"""Experimental RadioCaster custom encoder: PCM stdin -> Ogg/Opus stdout.

This module deliberately has no Qt imports and never opens a network connection.
RadioCaster owns audio capture and the source connection. FFmpeg must include
libopus. Native RadioCaster/Windows validation is still pending.
"""
import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib


class EncoderError(RuntimeError):
    pass


def transparent_png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0\0\0\0\0')) + chunk(b'IEND', b''))


def picture_tag(data, mime):
    # Xiph permits zero for unknown dimensions/depth. The image contains them.
    block = (struct.pack('>II', 3, len(mime)) + mime + struct.pack('>I', 0)
             + struct.pack('>IIIII', 0, 0, 0, 0, len(data)) + data)
    return base64.b64encode(block).decode('ascii')


CLEAR_PICTURE = picture_tag(transparent_png(), b'image/png')
TEXT_FIELDS = ('artist', 'title', 'album', 'album_artist', 'genre', 'year')


class MetadataReader:
    def __init__(self, path):
        self.path = Path(path)
        self._image_key = None
        self._image_tag = CLEAR_PICTURE
        self._file_key = None
        self._state = {}

    def _state_from_disk(self):
        try:
            stat = self.path.stat()
            key = stat.st_mtime_ns, stat.st_size
            if stat.st_size > 256 * 1024:
                raise ValueError('Metadata too large')
            if key != self._file_key:
                value = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(value, dict):
                    raise ValueError('Invalid object')
                self._state, self._file_key = value, key
            return self._state
        except (OSError, ValueError, TypeError):
            self._file_key, self._state = None, {}
            return {}

    def _art(self, name):
        try:
            if not isinstance(name, str) or not name or '\\' in name or any(part in ('.', '..') for part in name.split('/')):
                return CLEAR_PICTURE
            path = (self.path.parent / name).resolve()
            if path.parent not in (self.path.parent.resolve(), (self.path.parent / 'covers').resolve()):
                return CLEAR_PICTURE
            stat = path.stat()
            if not 0 < stat.st_size <= 4 * 1024 * 1024:
                return CLEAR_PICTURE
            key = path, stat.st_mtime_ns, stat.st_size
            if key != self._image_key:
                data = path.read_bytes()
                mime = (b'image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else
                        b'image/jpeg' if data.startswith(b'\xff\xd8\xff') else b'')
                self._image_tag = picture_tag(data, mime) if mime else CLEAR_PICTURE
                self._image_key = key
            return self._image_tag
        except OSError:
            return CLEAR_PICTURE

    def read(self, now=None):
        state = self._state_from_disk()
        music = False
        try:
            age = ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(state['updated_at'])).total_seconds()
            ttl = state['stale_seconds']
            music = (state.get('is_music') is True and type(ttl) is int and 1 <= ttl <= 300
                     and -60 <= age <= ttl and all(isinstance(state.get(key), str) and state[key].strip()
                                                  for key in ('artist', 'title')))
        except (KeyError, ValueError, TypeError):
            pass
        tags = {key: state.get(key, '') if music and isinstance(state.get(key, ''), str) else '' for key in TEXT_FIELDS}
        tags['date'] = tags.pop('year')
        tags['METADATA_BLOCK_PICTURE'] = self._art(state.get('artwork_file')) if music else CLEAR_PICTURE
        return tags


def escape_metadata(value):
    return (str(value).replace('\\', '\\\\').replace('\n', '\\\n').replace('=', '\\=')
            .replace(';', '\\;').replace('#', '\\#').replace('\r', ''))


def metadata_bytes(tags):
    return (';FFMETADATA1\n' + ''.join(f'{escape_metadata(key)}={escape_metadata(value)}\n'
                                     for key, value in tags.items())).encode('utf-8')


def find_ffmpeg(configured=''):
    if configured:
        return str(Path(configured).expanduser().resolve())
    executable = Path(sys.executable).resolve()
    candidates = [executable.parent / 'ffmpeg.exe']
    if len(executable.parents) > 2:
        candidates.append(executable.parents[2] / 'tools' / 'ffmpeg' / 'bin' / 'ffmpeg.exe')
    return next((str(path) for path in candidates if path.is_file()), shutil.which('ffmpeg') or '')


def check_ffmpeg(configured=''):
    executable = find_ffmpeg(configured)
    if not executable:
        raise EncoderError('Selecciona ffmpeg.exe en los ajustes del codificador de prueba.')
    try:
        result = subprocess.run([executable, '-hide_banner', '-encoders'], capture_output=True,
                                timeout=5, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or b'libopus' not in result.stdout:
            raise EncoderError('Ese FFmpeg no incluye el codificador libopus requerido.')
    except (OSError, subprocess.TimeoutExpired):
        raise EncoderError('No se pudo ejecutar FFmpeg. Revisa el archivo seleccionado.') from None
    return executable


def radiocaster_executable(path):
    """RadioCaster 3.7 failed to launch quoted executable paths on Windows."""
    path = str(path)
    if sys.platform != 'win32' or ' ' not in path:
        return path
    import ctypes
    from ctypes import wintypes
    get_short = ctypes.WinDLL('kernel32', use_last_error=True).GetShortPathNameW
    get_short.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
    get_short.restype = wintypes.DWORD
    size = get_short(path, None, 0)
    if size:
        buffer = ctypes.create_unicode_buffer(size)
        length = get_short(path, buffer, size)
        if 0 < length < size and ' ' not in buffer.value:
            return buffer.value
    raise EncoderError('RadioCaster necesita una ruta de Python sin espacios. Windows no ofrece una ruta abreviada para esta instalación; reinstala la app en una carpeta sin espacios.')


def command_line(metadata, ffmpeg):
    if getattr(sys, 'frozen', False):
        raise EncoderError('La prueba requiere la instalación Python; el EXE gráfico no sirve como codificador de consola.')
    return subprocess.list2cmdline([radiocaster_executable(sys.executable), '-u', '-m', 'radio_metadata.ogg_encoder',
        '--metadata', str(Path(metadata).resolve()), '--ffmpeg', str(ffmpeg),
        '--sample-rate', '{SampleRate}', '--channels', '{Channels}', '--bitrate', '{Bitrate}'])


def encode(metadata, sample_rate, channels, bitrate, executable, input_stream=None, output_stream=None):
    input_stream = input_stream if input_stream is not None else sys.stdin.buffer
    output_stream = output_stream if output_stream is not None else sys.stdout.buffer
    reader = MetadataReader(metadata)
    chunks = queue.Queue(maxsize=250)
    stopping = threading.Event()
    failures = []
    block_size = sample_rate * channels * 2 // 50

    def put(value):
        while not stopping.is_set():
            try:
                chunks.put(value, timeout=.2)
                return
            except queue.Full:
                pass

    def read_pcm():
        try:
            while not stopping.is_set():
                data = input_stream.read(block_size)
                if not data:
                    break
                put(data)
        except OSError:
            failures.append('No se pudo leer el audio de entrada.')
        finally:
            put(None)

    threading.Thread(target=read_pcm, daemon=True).start()
    process, pump, current_key = None, None, None

    def finish():
        nonlocal process, pump
        if process is None:
            return
        child, process = process, None
        try:
            try:
                child.stdin.close()
            except BrokenPipeError:
                pass
            code = child.wait(timeout=10)
            pump.join(timeout=3)
            if pump.is_alive() or code or failures:
                raise EncoderError('El codificador no pudo completar el bloque de audio.')
        except subprocess.TimeoutExpired:
            raise EncoderError('FFmpeg no terminó a tiempo.') from None
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            child.stdout.close()

    try:
        with tempfile.TemporaryDirectory(prefix='metadata-ogg-') as tmp:
            tags_file = Path(tmp) / 'tags.txt'
            while True:
                data = chunks.get()
                if data is None:
                    break
                if len(data) % (channels * 2):
                    raise EncoderError('El audio de entrada contiene una muestra incompleta.')
                if failures:
                    raise EncoderError('La salida del codificador se cerró.')
                tags = reader.read()
                key = tuple(tags.items())
                if key != current_key:
                    finish()
                    tags_file.write_bytes(metadata_bytes(tags))
                    arguments = [executable, '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'ffmetadata', '-i', str(tags_file), '-f', 's16le', '-ar', str(sample_rate),
                        '-ac', str(channels), '-i', 'pipe:0', '-map', '1:a:0', '-map_metadata', '0',
                        '-c:a', 'libopus', '-ar', '48000', '-b:a', str(bitrate) + 'k', '-frame_duration', '20',
                        '-application', 'audio', '-flush_packets', '1', '-page_duration', '20000', '-f', 'ogg', 'pipe:1']
                    process = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

                    def transfer(stream):
                        try:
                            while block := stream.read1(65536):
                                output_stream.write(block)
                                output_stream.flush()
                        except (OSError, ValueError):
                            failures.append('No se pudo escribir el audio de salida.')

                    pump = threading.Thread(target=transfer, args=(process.stdout,), daemon=True)
                    pump.start()
                    current_key = key
                try:
                    process.stdin.write(data)
                except BrokenPipeError:
                    raise EncoderError('FFmpeg dejó de recibir audio.') from None
            finish()
            if failures:
                raise EncoderError('La entrada o salida de audio no se completó.')
    finally:
        stopping.set()
        finish()


def main():
    parser = argparse.ArgumentParser(description='Codificador experimental para RadioCaster; salida Ogg/Opus binaria.')
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--ffmpeg', default='')
    parser.add_argument('--sample-rate', type=int, default=48000)
    parser.add_argument('--channels', type=int, default=2)
    parser.add_argument('--bitrate', type=int, default=128)
    parser.add_argument('--check', action='store_true', help='Comprobar FFmpeg sin leer audio ni emitir datos binarios')
    options = parser.parse_args()
    if options.sample_rate not in (8000, 12000, 16000, 24000, 44100, 48000) or options.channels not in (1, 2) or not 16 <= options.bitrate <= 512:
        parser.error('Parámetros de audio no compatibles con esta prueba.')
    try:
        executable = check_ffmpeg(options.ffmpeg)
        if options.check:
            print('FFmpeg con libopus disponible. Perfil de prueba; no se emitió audio.')
            return 0
        if os.name == 'nt':
            import msvcrt
            msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
            msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        encode(options.metadata, options.sample_rate, options.channels, options.bitrate, executable)
        return 0
    except (EncoderError, OSError):
        print('No se completó la codificación Ogg/Opus. Revisa FFmpeg, los parámetros y la entrada de audio.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
