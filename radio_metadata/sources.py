"""Read-only source adapters. Never infer playback from a window title."""
from .credentials import read_secret, secret_id

import asyncio
import base64
import os
import sys
from dataclasses import replace
from typing import Protocol

from defusedxml import ElementTree as ET
import httpx

from .model import Snapshot, inside

MAX_XML = 8 * 1024 * 1024


def nonnegative_int(value):
    try:
        number = int(value)
        return number if 0 <= number < 2**40 else None
    except (ValueError, TypeError, OverflowError):
        return None


class Source(Protocol):
    name: str

    async def poll(self) -> Snapshot: ...


def parse_playback(xml: bytes) -> Snapshot:
    if len(xml) > MAX_XML:
        raise ValueError("Respuesta demasiado grande")
    root = ET.fromstring(xml)
    playback = root.find("Playback")
    track = root.find("CurrentTrack/TRACK")
    if playback is None:
        raise ValueError("Falta Playback")
    # Documented values: play, pause, stop; unknown state fails closed.
    playing = playback.get("state", "").casefold() == "play"
    attrs = track.attrib if track is not None else {}
    return Snapshot("radioboss", playing, attrs.get("ARTIST", ""), attrs.get("TITLE", ""),
                    attrs.get("FILENAME", ""), album=attrs.get("ALBUM", ""),
                    year=attrs.get("YEAR", ""), genre=attrs.get("GENRE", ""),
                    duration_ms=nonnegative_int(playback.get("len")),
                    position_ms=nonnegative_int(playback.get("pos")))


class RadioBossSource:
    name = "radioboss"

    def __init__(self, config, credentials=None):
        self.config = config
        self.credentials = credentials

    async def _request(self, **params):
        password = read_secret(self.credentials, secret_id("radioboss", self.config.radioboss_url, self.config.radioboss_user), self.config.radioboss_password_env, managed=secret_id("radioboss", self.config.radioboss_url, self.config.radioboss_user) in self.config.managed_credentials)
        if not password:
            raise ValueError("Introduce la contraseña en Conexiones → RadioBOSS")
        params.update({"pass": password, "user": self.config.radioboss_user})
        # Do not log request URLs: RadioBOSS authenticates via query parameters.
        async with httpx.AsyncClient(timeout=3, follow_redirects=False, trust_env=False) as client:
            async with client.stream("GET", self.config.radioboss_url, params=params) as response:
                response.raise_for_status()
                data = bytearray()
                async for part in response.aiter_bytes():
                    data.extend(part)
                    if len(data) > MAX_XML:
                        raise ValueError("Respuesta demasiado grande")
                return bytes(data)

    async def _poll(self):
        current = parse_playback(await self._request(action="playbackinfo"))
        if not current.playing or not current.filename:
            return current
        if not inside(current.filename, self.config.music_folders):
            return current  # No need to fetch tags/artwork for unapproved folders.
        tags = ET.fromstring(await self._request(action="readtag", fn=current.filename, artwork="1"))
        file = tags.find("File")
        if file is None:
            raise ValueError("readtag no devolvió File")
        # Recheck the track after fetching tags; don't attach artwork from a previous song.
        check = parse_playback(await self._request(action="playbackinfo"))
        if (check.filename, check.artist, check.title, check.playing) != (current.filename, current.artist, current.title, True):
            return Snapshot(self.name, error="Cambio de pista; esperando siguiente lectura")
        art = b""
        raw = file.get("Artwork_Base64", "")
        if raw:
            try:
                art = base64.b64decode(raw, validate=True)
            except ValueError:
                pass  # Artwork failure must not discard valid text.
        return replace(current, kind=file.get("TypeIdentifier", ""), artwork=art,
                       album=file.get("Album", current.album), year=file.get("Year", current.year),
                       genre=file.get("Genre", current.genre), isrc=file.get("ISRC", ""),
                       duration_ms=nonnegative_int(file.get("Duration")) or current.duration_ms,
                       position_ms=check.position_ms,
                       artwork_origin="radioboss_tag" if art else "")

    async def poll(self):
        return replace(await self._poll(), available=True)


class SpotifyWindowsSource:
    name = "spotify"

    def __init__(self, config):
        self.config = config

    async def poll(self):
        if sys.platform != "win32":
            return Snapshot(self.name, error="Sesiones multimedia disponibles solo en Windows")
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
        )
        from winrt.windows.media import MediaPlaybackType
        from winrt.windows.storage.streams import DataReader

        manager = await Manager.request_async()
        sessions = [s for s in manager.get_sessions()
                    if self.config.spotify_app_id_contains.casefold() in s.source_app_user_model_id.casefold()]
        playing = [s for s in sessions if s.get_playback_info().playback_status == Status.PLAYING]
        if len(playing) > 1:
            return Snapshot(self.name, error="Varias sesiones Spotify reproduciendo; selecciona una en Windows")
        if not playing:
            return Snapshot(self.name, available=bool(sessions))
        session = playing[0]
        media = await session.try_get_media_properties_async()
        kind = "music" if media.playback_type == MediaPlaybackType.MUSIC else "unknown"
        art = b""
        if media.thumbnail:
            try:
                stream = await media.thumbnail.open_read_async()
                try:
                    if 0 < stream.size <= 4 * 1024 * 1024:
                        reader = DataReader(stream)
                        try:
                            size = await reader.load_async(stream.size)
                            buf = bytearray(size)
                            reader.read_bytes(buf)
                            art = bytes(buf)
                        finally:
                            reader.detach_stream()
                            reader.close()
                finally:
                    stream.close()
            except Exception:
                pass  # Text and playback can still be used without a thumbnail.
        # Fail closed if playback stopped while reading the thumbnail.
        active = session.get_playback_info().playback_status == Status.PLAYING
        check = await session.try_get_media_properties_async()
        if (check.artist, check.title, check.album_title) != (media.artist, media.title, media.album_title):
            return Snapshot(self.name, error="Cambio de pista; esperando siguiente lectura")
        duration = position = None
        try:
            timeline = session.get_timeline_properties()
            duration = nonnegative_int((timeline.end_time - timeline.start_time).total_seconds() * 1000)
            position = nonnegative_int((timeline.position - timeline.start_time).total_seconds() * 1000)
        except (AttributeError, ValueError, OSError):
            pass
        return Snapshot(self.name, active, media.artist, media.title, kind=kind, artwork=art,
                        album=media.album_title or "", album_artist=media.album_artist or "",
                        genre=", ".join(media.genres), track_number=nonnegative_int(media.track_number),
                        duration_ms=duration, position_ms=position,
                        artwork_origin="windows_thumbnail" if art else "")


class DemoSource:
    """Explicit synthetic data; selected only by --demo. No network."""
    def __init__(self, name, scenario):
        self.name, self.scenario = name, scenario

    async def poll(self):
        playing = self.scenario in (self.name, "both", "ad")
        if self.scenario == "silence":
            playing = False
        if self.name == "radioboss":
            ad = self.scenario == "ad"
            return Snapshot(self.name, playing, "Comerciante" if ad else "Artista de prueba",
                            "Anuncio de prueba" if ad else "Canción de prueba",
                            r"C:\Musica\demo.mp3", "Commercial" if ad else "Music",
                            album="Álbum de prueba", year="2026", genre="Pop", duration_ms=210000, position_ms=42000)
        return Snapshot(self.name, playing, "Artista de ejemplo", "Segunda canción", kind="music",
                        album="Álbum de ejemplo", album_artist="Artista de ejemplo", duration_ms=180000)


def make_sources(config, demo=False, scenario="radioboss", credentials=None):
    if demo:
        return [DemoSource(n, scenario) for n in ("radioboss", "spotify")]
    sources = []
    if config.radioboss_enabled:
        sources.append(RadioBossSource(config, credentials))
    if config.spotify_enabled:
        sources.append(SpotifyWindowsSource(config))
    return sources
