from dataclasses import dataclass
import ntpath
import re
import unicodedata


def clean(value: str) -> str:
    return " ".join("".join(c for c in value if not unicodedata.category(c).startswith("C")).split())[:500]


@dataclass(frozen=True)
class Snapshot:
    source: str
    playing: bool = False
    artist: str = ""
    title: str = ""
    filename: str = ""
    kind: str = ""
    artwork: bytes = b""
    error: str = ""
    album: str = ""
    album_artist: str = ""
    year: str = ""
    genre: str = ""
    isrc: str = ""
    duration_ms: int | None = None
    position_ms: int | None = None
    track_number: int | None = None
    artwork_origin: str = ""
    available: bool | None = None


@dataclass(frozen=True)
class Decision:
    text: str
    source: str
    reason: str
    song: Snapshot | None = None
    conflict: bool = False


def inside(filename, folders, *, recursive=True):
    # Windows paths, also when tests run on another OS. Boundary-aware, case-insensitive.
    file = ntpath.normcase(ntpath.normpath(filename))
    for folder in folders:
        root = ntpath.normcase(ntpath.normpath(folder))
        try:
            if not recursive:
                if ntpath.isabs(file) and ntpath.isabs(root) and ntpath.dirname(file) == root:
                    return True
                continue
            if ntpath.isabs(file) and ntpath.isabs(root) and ntpath.commonpath([file, root]) == root:
                return True
        except ValueError:
            pass
    return False


def effective_folder_rules(config):
    if config.folder_rules:
        return config.folder_rules
    return ([dict(path=path, action='allow', recursive=True) for path in config.music_folders]
            + [dict(path=path, action='block', recursive=True) for path in config.excluded_folders])


def folder_allowed(filename, config):
    matched = [rule['action'] for rule in effective_folder_rules(config)
               if inside(filename, [rule['path']], recursive=rule['recursive'])]
    return 'allow' in matched and 'block' not in matched


def valid_music(track, config):
    artist, title = clean(track.artist), clean(track.title)
    invalid = {"unknown", "unknown artist", "unknown title", "desconocido", "artista desconocido", "título desconocido", "untitled", "n/a", "-"}
    if not artist or not title or artist.casefold() in invalid or title.casefold() in invalid:
        return False
    words = f"{artist} {title} {track.filename}".casefold()
    if any(re.search(r"(?<!\w)" + re.escape(t.casefold()) + r"(?!\w)", words) for t in config.excluded_terms):
        return False
    if any(t.casefold() in track.kind.casefold() for t in config.excluded_types):
        return False
    if track.source == "radioboss":
        return folder_allowed(track.filename, config)
    if track.source == "spotify":
        return config.spotify_publish and track.kind == "music"
    source = next((item for item in config.windows_sources if item['id'] == track.source), None)
    if source:
        return (source['enabled'] and source['publish'] and
                (track.kind == 'music' or (source['allow_unknown'] and track.kind == 'unknown')))
    return False


def resolve(snapshots, config, mode="auto"):
    if mode == "station":
        return Decision(config.break_message, "estación", "Modo de pausa activado")
    candidates = [t for t in snapshots if t.playing and not t.error]
    conflict = len(candidates) > 1
    if mode != "auto":
        chosen = next((t for t in candidates if t.source == mode), None)
    else:
        from .source_catalog import source_order
        by_source = {track.source: track for track in candidates}
        chosen = next((by_source[key] for key in source_order(config) if key in by_source), None)
    if chosen is None:
        return Decision(config.idle_message, "estación", "Sin reproducción válida o fuente no disponible", conflict=conflict)
    # Resolve source BEFORE filtering. An ad in the selected source must never reveal a lower-priority song.
    if not valid_music(chosen, config):
        return Decision(config.break_message, chosen.source, "Contenido excluido, sin clasificar o solo observación", conflict=conflict)
    return Decision(f"{clean(chosen.artist)} - {clean(chosen.title)}", chosen.source,
                    "Prioridad configurada; comprobar consola" if conflict else "Reproducción detectada; comprobar consola",
                    chosen, conflict)
