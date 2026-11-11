"""Stable source identities and priority, shared by the engine and interface."""
import hashlib


def windows_source_id(app_id):
    return 'windows-' + hashlib.sha256(app_id.casefold().encode('utf-8')).hexdigest()[:16]


def windows_app_name(app_id):
    value = app_id.casefold()
    for fragment, label in [('spotify', 'Spotify'), ('deezer', 'Deezer'), ('vlc', 'VLC'),
                            ('zunemusic', 'Reproductor multimedia de Windows'),
                            ('wmplayer', 'Windows Media Player'), ('winamp', 'Winamp'),
                            ('foobar2000', 'foobar2000'), ('msedge', 'Microsoft Edge'),
                            ('chrome', 'Google Chrome'), ('firefox', 'Firefox')]:
        if fragment in value:
            return label
    return app_id.replace('\\', '/').rsplit('/', 1)[-1].split('!')[0][:100]


def configured_sources(config):
    return [dict(id='radioboss', name='RadioBOSS', enabled=config.radioboss_enabled, publish=True),
            dict(id='spotify', name='Spotify', enabled=config.spotify_enabled, publish=config.spotify_publish),
            *[dict(item) for item in config.windows_sources]]


def source_order(config):
    known = [item['id'] for item in configured_sources(config)]
    preferred = config.source_priority or [config.priority]
    return list(dict.fromkeys([key for key in preferred if key in known] + known))


def source_label(key, config=None):
    if config:
        found = next((item for item in configured_sources(config) if item['id'] == key), None)
        if found:
            return found['name']
    return {'radioboss': 'RadioBOSS', 'spotify': 'Spotify', 'estación': 'Estación'}.get(
        key, 'Reproductor de Windows' if key.startswith('windows-') else key)
