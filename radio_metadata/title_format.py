"""Text templates only: no expressions, attribute access or executable code."""
from string import Formatter

FIELDS = {'title', 'artist', 'album', 'album_artist', 'year', 'genre'}


def validate_format(template):
    if not isinstance(template, str) or not template.strip() or len(template) > 250 or any(ord(c) < 32 for c in template):
        raise ValueError('Escribe un formato de título de una sola línea, hasta 250 caracteres.')
    found = []
    try:
        for _, field, spec, conversion in Formatter().parse(template):
            if field is not None:
                if field not in FIELDS or spec or conversion:
                    raise ValueError()
                found.append(field)
        if 'title' not in found:
            raise ValueError()
    except ValueError:
        raise ValueError('Incluye {title}. Campos disponibles: {title}, {artist}, {album}, {album_artist}, {year}, {genre}. Sin expresiones ni modificadores.') from None


def format_title(track, template):
    from .model import clean
    validate_format(template)
    return clean(template.format(**{field: clean(getattr(track, field)) for field in FIELDS}))
