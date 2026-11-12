# Monitoreo y estadísticas

La pestaña **Monitoreo** separa la recepción de audio, las estadísticas del servidor y el historial de incidentes. No controla el emisor, no altera la selección de fuente y no reintroduce conexiones de publicación a proveedores.

## Audio y silencio

1. Selecciona FFmpeg desde **Ajustes → Codificador**.
2. En **Carátulas**, configura el enlace público de audio que quieras comprobar.
3. En **Ajustes → Monitoreo**, activa la comprobación de audio.
4. Guarda y consulta **Monitoreo → Comprobar ahora**.

Por defecto toma 5 segundos de audio cada 60 segundos, decodifica a PCM estéreo de 8 kHz y mide la energía RMS en bloques de 100 ms. Detecta silencio cuando al menos 3 segundos consecutivos de la muestra están por debajo de −50 dBFS. Se mantienen ambos canales para evitar confundir una señal estéreo en contrafase con silencio por cancelación al mezclarla a mono. El análisis no reproduce sonido por los altavoces.

El intervalo se configura entre 15 y 300 segundos, la muestra entre 3 y 10 segundos, el silencio mínimo entre 1 y 10 segundos y el umbral entre −90 y −10 dBFS. El silencio mínimo no puede superar la muestra. FFmpeg tiene límites de espera; una muestra incompleta, una desconexión o un error de decodificación se informa como error, no como silencio confirmado.

Las comprobaciones trabajan en paralelo al procesamiento de metadatos. No es monitoreo continuo: un fallo entre muestras puede pasar inadvertido. La periodicidad real también depende del ciclo de consultas de fuentes. La medición corresponde a esta computadora y esta dirección, no a varios países ni a todos los oyentes. Cada prueba abre una conexión de escucha, consume ancho de banda y puede incrementar temporalmente el conteo de oyentes del servidor.

## Estadísticas de oyentes

Activa la consulta opcional de estadísticas y configura la URL completa de un servicio JSON. Opciones:

- **JSON genérico:** `{"listeners": 12}`. El conteo debe ser entero no negativo. Se admite `online: false` para indicar indisponibilidad.
- **Icecast status-json:** URL del endpoint JSON de estadísticas y punto de montaje exacto. Solo usa el conteo de ese montaje, no suma señales duplicadas.
- **AzuraCast Now Playing:** URL pública del endpoint de la estación; usa `listeners.current` cuando está online.

Es una integración exclusivamente de lectura. No necesita contraseñas de emisión. Si el endpoint requiere un token Bearer, se guarda desde Ajustes en el almacén de Windows, separado de la configuración. Las direcciones remotas requieren HTTPS; HTTP se permite solo en pruebas locales. **Probar conexión** consulta el conteo sin emitir ni modificar metadatos.

Se muestran el conteo de la última muestra válida, las últimas 20 mediciones válidas y el pico y promedio de muestras de las últimas 24 horas. Son oyentes simultáneos comunicados por el servidor: no oyentes únicos, no tiempo total de escucha y no un promedio ponderado por duración. Un fallo queda como dato desconocido y no se agrega como cero. Al cambiar de endpoint o montaje no se mezclan sus medidas con las anteriores.

## Incidentes y conservación

Por defecto se requieren dos resultados consecutivos del mismo problema para abrir un incidente, y dos resultados correctos para cerrarlo. Se puede elegir de uno a cinco. Las lecturas fallidas aisladas aparecen en el estado actual, pero no necesariamente abren un incidente. Se detectan silencio en la muestra, error de recepción/decodificación y error de estadísticas.

Se guarda inicio, fin, servicio, estado y una descripción sin claves ni respuestas de servidores. Desactivar una comprobación o cambiar su configuración cierra el incidente abierto con esa explicación; no se presenta como recuperación verificada. Los incidentes abiertos persisten al reiniciar. La interfaz muestra los 200 más recientes y permite exportarlos a CSV.

La base local `monitor.sqlite3` conserva muestras e incidentes cerrados durante 30 días inicialmente, ajustables entre 1 y 365 días. Hay topes adicionales de 100 000 muestras y 10 000 incidentes para limitar el crecimiento. No se borra el historial musical. La demo usa su propia base y nunca abre comprobaciones reales. Las consultas de estadísticas no dependen de peticiones al JSON del receptor ni se cuentan como oyentes de la emisora.

## Compatibilidad en Windows

La prueba local con FFmpeg comprueba recepción HTTP, audio normal y silencio. Para validar en tu equipo:

1. Actualiza la app y elige tu `ffmpeg.exe`.
2. Comprueba la fuente de música en **Ajustes → Fuentes** con cada reproductor abierto.
3. En **Now Playing**, elige **Artista - Canción** en **Formato del título combinado** y comprueba que coincidan TXT, XML/CASTTITLE y JSON/text. Los campos separados de artista y título deben mantenerse correctos.
4. Activa el monitoreo con una dirección de prueba. Comprueba recepción y las fechas de consulta.
5. Para probar silencio o desconexiones, usa un stream de prueba separado. No detengas una emisión en vivo para ensayar.
6. Configura la API de estadísticas y compara el conteo con su panel, teniendo en cuenta el intervalo y la propia conexión de prueba.

El instalador, la distribución de FFmpeg y el despliegue del receptor se mantienen para el final.

## Referencias técnicas

- [Protocolos y límites de espera de FFmpeg](https://ffmpeg.org/ffmpeg-protocols.html).
- [Estadísticas oficiales de Icecast y endpoint JSON](https://www.icecast.org/docs/icecast-latest/server_stats/).
