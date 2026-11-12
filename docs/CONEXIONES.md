# Fuentes, salidas y aplicación de transmisión

MetaDATA prepara información musical independientemente del emisor. La captura de audio, las conexiones con servidores y las contraseñas de emisión pertenecen al programa de transmisión elegido. No hace falta introducir credenciales de AzuraCast, Zeno.fm ni Icecast en MetaDATA.

## Fuentes

- **RadioBOSS:** configura la API HTTP local, usuario cuando corresponda y contraseña desde Conexiones → RadioBOSS. La consulta obtiene estado, metadatos y portada disponibles. No controla la reproducción.
- **Spotify:** consulta las sesiones multimedia de Windows. No requiere una clave API; necesita que la aplicación exponga una sesión. La clasificación de anuncios tiene límites y no identifica infaliblemente el audio que sale de una consola.

La prioridad se configura en Ajustes → Fuentes; las carpetas y exclusiones, en Ajustes → Reglas. Pausar metadatos vacía los campos musicales y los anuncios excluidos no entran al historial.

## Now Playing: archivos para tu emisor

Desde Conexiones → **Now Playing**, o Ajustes → **Now Playing**, puedes elegir formato, copiar la ruta y abrir su carpeta:

| Salida | Contenido | Cómo integrarla |
| --- | --- | --- |
| `nowplaying.txt` | Título combinado (Artista - Canción por defecto), UTF-8; línea vacía en pausas | Programa que lea el título de un archivo de texto |
| `nowplaying.xml` | Atributos musicales separados y `TRACK/CASTTITLE` combinado | Configurar la plantilla que admita el lector XML del emisor |
| `nowplaying.json` | Esquema propio de MetaDATA con datos musicales y referencia a imagen | Integración o reproductor que conozca esos campos |
| `covers/` | Imágenes separadas de los archivos de texto | El consumidor necesita un mecanismo para leer o publicar imágenes |

La disponibilidad de un archivo no confirma que el emisor lo haya leído o que esté al aire. Tampoco implica que cualquier programa entienda nuestro XML o JSON. El formato se elige según las capacidades documentadas del receptor.

Ejemplo específico de RadioCaster: seleccionar **Read from XML file**, indicar `nowplaying.xml` y escribir `{TRACK[CASTTITLE]}` en Title Format. No usar un guion fijo entre artista y título vacíos. Eso forma un título textual; no envía todos los campos XML ni la portada automáticamente.

## Codificador externo

Ajustes → **Codificador** permite generar AAC principal, MP3 de respaldo u Ogg experimental. El comando general usa valores numéricos de frecuencia de entrada, canales y bitrate elegidos allí, sin marcadores de una marca. El programa anfitrión debe aceptar un codificador externo por consola y cumplir este contrato:

- Entrada: audio PCM con signo, 16 bits, little-endian, por STDIN. La frecuencia y canales deben coincidir con los del comando.
- Salida: AAC/ADTS, MP3 u Ogg/Opus por STDOUT, según la selección.
- El anfitrión aporta audio y gestiona la conexión. El módulo no captura dispositivos ni transmite a un servidor por sí mismo.

Si un emisor no admite este contrato, puede usar las salidas de archivos que soporte. No se afirma compatibilidad universal ni se presume soporte de codificadores externos en otros programas.

La opción **Usar variables de RadioCaster en el comando** adapta la línea a `{SampleRate}`, `{Channels}` y `{Bitrate}` y busca la ruta abreviada de Python en Windows. Es una integración opcional. Las conexiones ya guardadas en ese emisor no se modifican al cambiar esta opción.

AAC/MP3 directos no incluyen portada dinámica. La opción HLS local con ID3/APIC se explica, junto con sus límites y validación pendiente, en [la guía AAC/HLS](PRUEBA-AAC-WINDOWS.md). Ogg conserva la prueba de portadas para receptores compatibles.

## Portadas y publicación

Las portadas siguen obteniéndose de las fuentes y guardándose en covers. La caché local se limita por historial visible y espacio configurados. Publicación permite enviar los metadatos y la imagen juntos al receptor autohospedado; no requiere una URL de audio en MetaDATA.

## Configuraciones anteriores

Se retiraron las conexiones AzuraCast y Zeno.fm de la pantalla Conexiones, la página Icecast directo y el monitor de servidores. El motor ignora las antiguas salidas directas incluso si estaban activadas en el perfil. Al guardar ajustes se desactivan sus indicadores, conservando las direcciones históricas y las credenciales guardadas; no se borran claves ni se cambian servidores o conexiones del emisor.

Los conectores e investigaciones antiguos pueden seguir presentes como código/documentación de referencia, pero no forman parte del flujo activo de la app. Para poner la estación al aire se configura el destino en el emisor elegido.

Un único formato controla el título combinado de todas las salidas. XML/DISPLAYTITLE y JSON/display_text son alias del mismo texto. Para receptores que interpretan ese texto se recomienda Artista - Canción; cambiar su orden puede invertir los campos. Consulta la [unificación de formatos](NOVEDADES-0.5.0a5.md).

El monitoreo, las estadísticas y el reproductor local se retiraron de MetaDATA. No se requiere un enlace de audio. Las portadas de las canciones se conservan y se pueden enviar con los metadatos mediante Publicación.
