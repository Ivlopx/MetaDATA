"""Owned image cache: count/size limits and references to visible history."""
import hashlib
from pathlib import Path
import re

NAME = re.compile(r'artwork-[a-f0-9]{24}\.(png|jpg|webp)')


def image_type(data):
    if not data or len(data) > 4 * 1024 * 1024:
        return None
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png', 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'jpg', 'image/jpeg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp', 'image/webp'
    return None


def asset_name(data):
    kind = image_type(data)
    return f'covers/artwork-{hashlib.sha256(data).hexdigest()[:24]}.{kind[0]}' if kind else ''


def owned_files(directory):
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return [path for path in directory.iterdir() if NAME.fullmatch(path.name) and path.is_file() and not path.is_symlink()]


def migrate_images(directory):
    directory = Path(directory)
    target = directory / 'covers'
    target.mkdir(parents=True, exist_ok=True)
    for old in owned_files(directory):
        # Move only images whose content matches the application's own hash name.
        data = old.read_bytes()
        name = asset_name(data)
        if name and Path(name).name == old.name:
            destination = directory / name
            if destination.exists():
                if destination.read_bytes() == data:
                    old.unlink()
            else:
                old.replace(destination)


def cache_usage(directory):
    count, size = 0, 0
    for path in owned_files(Path(directory) / 'covers'):
        try:
            length = path.stat().st_size
        except OSError:
            continue
        count += 1
        size += length
    return count, size


def prune_images(directory, current, visible_history, max_items, max_bytes):
    files = {path.name: path for path in owned_files(Path(directory) / 'covers')}
    protected = {Path(name).name for name in current if name}
    keep = set(protected) & files.keys()
    size = sum(files[name].stat().st_size for name in keep)
    if visible_history is None:
        order = [path.name for path in sorted(files.values(), key=lambda path: path.stat().st_mtime_ns, reverse=True)]
    else:
        order = [Path(name).name for name in visible_history if name]
    for name in dict.fromkeys(order):
        if name not in files or name in keep:
            continue
        length = files[name].stat().st_size
        if len(keep) < max_items and size + length <= max_bytes:
            keep.add(name)
            size += length
    for name, path in files.items():
        if name not in keep:
            path.unlink(missing_ok=True)
