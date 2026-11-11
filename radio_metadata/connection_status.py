"""Presentation states reflect evidence, never inferred audio routing."""
from .source_catalog import configured_sources


def connection_states(config, snapshots, statuses, remote_records, *, demo=False, mode='auto', local_exists=False):
    result = {}
    observed = {snapshot.source: snapshot for snapshot in snapshots}
    for row in configured_sources(config):
        source, enabled = row['id'], row['enabled']
        label = row['name'] if source in ('radioboss', 'spotify') else source
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
    receiver_error = any(text.startswith('Error de publicación:') for text in statuses)
    confirmed = any(text.startswith('Receptor:') and 'confirmad' in text for text in statuses)
    result['Receptor'] = (('unknown', 'Desactivado' if not config.receiver_enabled else 'Demostración · no se publica')
                          if not config.receiver_enabled or demo else
                          ('error', 'No se pudo confirmar el envío · reintentando') if receiver_error else
                          ('ok', 'Ficha confirmada por el receptor') if confirmed else
                          ('unknown', 'Esperando confirmación'))
    result['Now Playing'] = (('error', 'No se pudo actualizar el archivo de títulos') if local_error else
                             ('warning', 'Archivos listos · lectura por el emisor sin comprobar') if local_exists else
                             ('unknown', 'Esperando archivo de títulos'))
    return result
