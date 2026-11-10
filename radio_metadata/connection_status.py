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
    result['RadioCaster'] = (('error', 'No se pudo actualizar el archivo de títulos') if local_error else
                             ('warning', 'Archivo listo · conexión del encoder sin comprobar') if local_exists else
                             ('unknown', 'Esperando archivo de títulos'))
    result['AzuraCast'] = 'unknown', 'Mediante RadioCaster · sin comprobación remota'
    if config.remote_monitor_enabled and not demo:
        record = next((item for item in remote_records if item['service'] == 'AzuraCast'), None)
        if record:
            if record['error']:
                result['AzuraCast'] = 'error', record['error']
            elif not record['online']:
                result['AzuraCast'] = 'error', 'El servidor informa estación fuera de línea'
            elif record['matches']:
                result['AzuraCast'] = 'ok', 'En línea · título coincide en la última consulta'
            else:
                result['AzuraCast'] = 'warning', 'En línea · título diferente; puede haber retardo'
        else:
            result['AzuraCast'] = 'unknown', 'Esperando comprobación remota'
    result['Zeno.fm'] = 'unknown', 'Encoder en RadioCaster · sin comprobación automática'
    return result
