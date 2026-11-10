"""PCM -> continuous AAC/ADTS (primary) or MP3 (fallback) for RadioCaster.

Optional local HLS segments contain ID3 metadata and the actual picture. Raw AAC
stdout deliberately contains no injected pictures: ordinary Icecast AAC players
are not assumed to interpret changing ID3. No network or Qt dependencies.
"""
import argparse
import base64
import math
import os
import re
from pathlib import Path
import struct
import subprocess
import sys
import threading
import uuid

from .config import atomic_write
from .ogg_encoder import (EncoderError, MetadataReader, find_ffmpeg,
                          radiocaster_executable)

FORMATS = {'aac': ('aac', 'adts', 'audio/aac'),
           'mp3': ('libmp3lame', 'mp3', 'audio/mpeg')}


def check_ffmpeg(configured='', audio_format='aac'):
    executable = find_ffmpeg(configured)
    codec = FORMATS[audio_format][0]
    try:
        result = subprocess.run([executable, '-hide_banner', '-encoders'], capture_output=True,
                                timeout=5, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired):
        raise EncoderError('No se pudo ejecutar FFmpeg. Revisa el archivo seleccionado.') from None
    if result.returncode or not any(len(line.split()) > 1 and line.split()[1] == codec.encode()
                                    for line in result.stdout.splitlines()):
        raise EncoderError(f'FFmpeg no incluye el codificador {codec}.')
    return executable


def command_line(metadata, ffmpeg, audio_format='aac', hls=False):
    if getattr(sys, 'frozen', False):
        raise EncoderError('El codificador requiere la instalación Python de consola.')
    args = [radiocaster_executable(sys.executable), '-u', '-m', 'radio_metadata.aac_encoder',
            '--format', audio_format, '--metadata', str(Path(metadata).resolve()),
            '--ffmpeg', str(ffmpeg), '--sample-rate', '{SampleRate}', '--channels', '{Channels}',
            '--bitrate', '{Bitrate}']
    if hls:
        if audio_format != 'aac':
            raise EncoderError('La prueba HLS requiere AAC.')
        args += ['--hls-dir', str(Path(metadata).resolve().parent / 'hls')]
    return subprocess.list2cmdline(args)


def synchsafe(number):
    if not 0 <= number < 1 << 28:
        raise EncoderError('Etiqueta ID3 demasiado grande.')
    return bytes((number >> shift) & 127 for shift in (21, 14, 7, 0))


def id3_frame(name, payload):
    return name.encode('ascii') + synchsafe(len(payload)) + b'\0\0' + payload


def id3_tags(tags, timestamp):
    # RFC 8216 section 3.4: packed audio needs this 33-bit timestamp in ID3 PRIV.
    frames = [id3_frame('PRIV', b'com.apple.streaming.transportStreamTimestamp\0'
                        + struct.pack('>Q', timestamp % (1 << 33)))]
    for key, frame in (('title', 'TIT2'), ('artist', 'TPE1'), ('album', 'TALB'),
                       ('album_artist', 'TPE2'), ('genre', 'TCON'), ('date', 'TDRC')):
        frames.append(id3_frame(frame, b'\x03' + tags.get(key, '').replace('\0', '').encode('utf-8')))
    # Decode the bounded FLAC picture block supplied by MetadataReader.
    picture = base64.b64decode(tags['METADATA_BLOCK_PICTURE'], validate=True)
    mime_size = struct.unpack_from('>I', picture, 4)[0]
    mime = picture[8:8 + mime_size]
    position = 8 + mime_size
    description_size = struct.unpack_from('>I', picture, position)[0]
    position += 4 + description_size + 16
    size = struct.unpack_from('>I', picture, position)[0]
    image = picture[position + 4:position + 4 + size]
    if mime not in (b'image/png', b'image/jpeg') or len(image) != size:
        raise EncoderError('Portada no compatible con ID3.')
    frames.append(id3_frame('APIC', b'\x03' + mime + b'\0\x03\0' + image))
    data = b''.join(frames)
    return b'ID3\x04\0\0' + synchsafe(len(data)) + data


class HLSSegments:
    """Bounded six-second packed AAC segments, independent of direct stdout."""
    def __init__(self, directory, metadata, seconds=6, window=6):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = (self.directory / '.encoder.lock').open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.lock.seek(0)
                if not self.lock.read(1):
                    self.lock.write(b'0')
                    self.lock.flush()
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise EncoderError('Ya existe un codificador HLS usando esta carpeta.') from None
        self.reader = MetadataReader(metadata)
        self.seconds, self.window = seconds, window
        self.session = uuid.uuid4().hex[:16]
        self.buffer, self.frames = bytearray(), bytearray()
        self.duration, self.elapsed, self.start = 0., 0., 0.
        self.tags, self.entries, self.retired = None, [], []
        self.sequence = 0
        self.rate = None
        # Remove only this helper's previous generated files; use one helper per profile.
        for path in self.directory.glob('segment-*.aac'):
            if re.fullmatch(r'segment-[a-f0-9]{16}-[0-9]{8}\.aac', path.name):
                path.unlink(missing_ok=True)
        (self.directory / 'live.m3u8').unlink(missing_ok=True)

    def feed(self, data):
        self.buffer.extend(data)
        while len(self.buffer) >= 7:
            header = self.buffer
            if header[0] != 255 or header[1] & 0xf6 != 0xf0:
                raise EncoderError('FFmpeg no produjo audio AAC/ADTS válido.')
            index = (header[2] >> 2) & 15
            rates = (96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350)
            if index >= len(rates):
                raise EncoderError('Frecuencia AAC no compatible.')
            rate = rates[index]
            if self.rate is not None and rate != self.rate:
                raise EncoderError('La frecuencia AAC cambió durante la emisión.')
            self.rate = rate
            length = ((header[3] & 3) << 11) | (header[4] << 3) | (header[5] >> 5)
            if length < (7 if header[1] & 1 else 9):
                raise EncoderError('Trama AAC incompleta.')
            if len(header) < length:
                break
            duration = 1024 * ((header[6] & 3) + 1) / rate
            if not self.frames:
                self.tags = self.reader.read()
                self.start = self.elapsed
            self.frames.extend(header[:length])
            del self.buffer[:length]
            self.duration += duration
            self.elapsed += duration
            if self.duration >= self.seconds:
                self.publish()

    def publish(self, final=False):
        if self.frames:
            name = f'segment-{self.session}-{self.sequence:08d}.aac'
            atomic_write(self.directory / name, id3_tags(self.tags, round(self.start * 90000)) + self.frames)
            self.entries.append((self.sequence, name, self.duration))
            self.sequence += 1
            self.frames.clear()
            self.duration = 0.
        if not self.entries:
            return
        while len(self.entries) > self.window:
            self.retired.append((self.sequence, self.entries.pop(0)[1]))
        lines = ['#EXTM3U', '#EXT-X-VERSION:3', f'#EXT-X-TARGETDURATION:{math.ceil(self.seconds + .15)}',
                 f'#EXT-X-MEDIA-SEQUENCE:{self.entries[0][0]}']
        for _, name, duration in self.entries:
            lines += [f'#EXTINF:{duration:.6f},', name]
        if final:
            lines.append('#EXT-X-ENDLIST')
        atomic_write(self.directory / 'live.m3u8', ('\n'.join(lines) + '\n').encode())
        # Keep evicted segments for another full playlist duration for in-flight clients.
        remaining = []
        for retired_at, name in self.retired:
            if self.sequence - retired_at >= self.window + 1:
                (self.directory / name).unlink(missing_ok=True)
            else:
                remaining.append((retired_at, name))
        self.retired = remaining

    def close(self):
        try:
            if self.buffer:
                raise EncoderError('FFmpeg terminó con una trama AAC incompleta.')
            self.publish(final=True)
        finally:
            self.release()

    def release(self):
        if not self.lock.closed:
            self.lock.close()


def encode(metadata, sample_rate, channels, bitrate, executable, audio_format='aac',
           hls_directory=None, input_stream=None, output_stream=None):
    if hls_directory and audio_format != 'aac':
        raise EncoderError('La prueba HLS requiere AAC.')
    source = input_stream if input_stream is not None else sys.stdin.buffer
    sink = output_stream if output_stream is not None else sys.stdout.buffer
    codec, container, _ = FORMATS[audio_format]
    args = [executable, '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-f', 's16le', '-ar', str(sample_rate), '-ac', str(channels), '-i', 'pipe:0',
            '-map', '0:a:0', '-c:a', codec, '-b:a', f'{bitrate}k', '-flush_packets', '1']
    if audio_format == 'aac':
        args += ['-profile:a', 'aac_low']
    else:
        args += ['-write_xing', '0', '-id3v2_version', '0']
    args += ['-f', container, 'pipe:1']
    hls = None
    failures = []
    child = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        hls = HLSSegments(hls_directory, metadata) if hls_directory else None
    except BaseException:
        child.kill()
        child.wait()
        child.stdin.close()
        child.stdout.close()
        raise

    def transfer():
        try:
            while data := child.stdout.read1(65536):
                sink.write(data)
                sink.flush()
                if hls:
                    hls.feed(data)
            if hls:
                hls.close()
        except (OSError, ValueError, EncoderError) as error:
            failures.append(error)
            child.kill()

    pump = threading.Thread(target=transfer, daemon=True)
    pump.start()
    try:
        while data := source.read(sample_rate * channels * 2 // 50):
            child.stdin.write(data)
        child.stdin.close()
        code = child.wait(timeout=10)
        pump.join(timeout=5)
        if code or failures or pump.is_alive():
            raise EncoderError('No se completó la salida AAC/MP3. Revisa FFmpeg y la carpeta HLS.')
    except (BrokenPipeError, subprocess.TimeoutExpired):
        raise EncoderError('FFmpeg dejó de recibir audio o no terminó a tiempo.') from None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        child.stdin.close()
        child.stdout.close()
        pump.join(timeout=2)
        if hls:
            hls.release()


def main():
    parser = argparse.ArgumentParser(description='AAC principal / MP3 de respaldo para RadioCaster. HLS con ID3 experimental.')
    parser.add_argument('--format', choices=FORMATS, default='aac')
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--ffmpeg', default='')
    parser.add_argument('--sample-rate', type=int, choices=(32000, 44100, 48000), default=48000)
    parser.add_argument('--channels', type=int, choices=(1, 2), default=2)
    parser.add_argument('--bitrate', type=int, default=128)
    parser.add_argument('--hls-dir', type=Path)
    parser.add_argument('--check', action='store_true')
    options = parser.parse_args()
    if not 32 <= options.bitrate <= 320 or (options.hls_dir and options.format != 'aac'):
        parser.error('Usa 32–320 kbps; HLS solo se genera desde AAC.')
    try:
        executable = check_ffmpeg(options.ffmpeg, options.format)
        if options.check:
            print(f'FFmpeg con {options.format.upper()} disponible. No se emitió audio.')
            return 0
        if os.name == 'nt':
            import msvcrt
            msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
            msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        encode(options.metadata, options.sample_rate, options.channels, options.bitrate,
               executable, options.format, options.hls_dir)
        return 0
    except (EncoderError, OSError) as error:
        print(f'No se pudo completar la codificación: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
