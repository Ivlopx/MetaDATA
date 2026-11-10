"""Presentation states reflect evidence, never inferred audio routing."""


def connection_states(config, snapshots, statuses, remote_records, *, demo=False, mode='auto', local_exists=False):
    result = {}
    observed = {snapshot.source: snapshot for snapshot in snapshots}
    for source, label, enabled in [('radioboss', 'RadioBOSS', config.radioboss_enabled), ('spotify', 'Spotify', config.spotify_enabled)]:
        snapshot = observed.get(source)
        if demo:
            result[label] = 'unknown', 'Demostración · ' + ('reproduciendo' if snapshot and snapshot.playing else 'sin reproducción')
        elif mode == 'station':
            result[label] = 'unknown', 'Consulta suspendida durante la pausa de metadatos'
        elif not enabled:
            result[label] = 'unknown', 'Desactivado'
        elif snapshot is None:
            result[label] = 'unknown', 'Esperando comprobación'
        elif snapshot.error:
            result[label] = 'error', snapshot.error
        elif snapshot.available is False:
            result[label] = 'error', 'No hay una sesión disponible'
        elif snapshot.playing:
            result[label] = 'ok', 'Reproducción detectada · última consulta correcta'
        elif snapshot.available is True:
            result[label] = 'ok', 'Disponible · en pausa o detenido'
        else:
            result[label] = 'unknown', 'Sin reproducción · disponibilidad sin confirmar'
    local_error = any(text.startswith('Error de salida local:') for text in statuses)
    result['Now Playing'] = (('error', 'No se pudo actualizar el archivo de títulos') if local_error else
                             ('warning', 'Archivos listos · lectura por el emisor sin comprobar') if local_exists else
                             ('unknown', 'Esperando archivo de títulos'))
    return result
