# AAC con artista, título, álbum y portada en vivo

Investigación y pruebas del **10 de noviembre de 2026**. Objetivo: conservar AAC como audio principal y MP3 de reserva, y ofrecer una salida que transporte la ficha musical completa dentro de la misma entrega de audio. Mantener MetaDATA independiente del emisor y del proveedor de radio.

## Decisión

**AAC + HLS Packed Audio + ID3/APIC es la ruta validada para nuestro reproductor web.** El usuario abre una URL `.m3u8` y pulsa reproducir una sola vez. El navegador descarga la lista y sus segmentos AAC; los segmentos contienen el audio y los datos, incluidos los bytes de la portada. No necesita consultar Now Playing, una API de carátulas ni un archivo de imagen aparte para mostrar la ficha. Sí necesita un lector de esas etiquetas: la prueba usó hls.js y la página del laboratorio.

Conservar **AAC/ADTS directo** para apps y directorios que solo aceptan una URL de audio, y **MP3** de respaldo. En esas salidas usar el título que ya transmite el emisor cuando el destino lo admita. Ogg/Opus sigue siendo una alternativa verificada para VLC. La conclusión no convierte la URL `.aac` existente en un enlace con portada ni acredita compatibilidad universal con HLS.

## Qué distingue cada formato

| Ruta | Qué puede transportar | Resultado para MetaDATA |
| --- | --- | --- |
| AAC/ADTS + bloques ID3v2.4/APIC intercalados | Audio AAC, campos separados e imagen binaria | Se construyó un flujo continuo y FFmpeg lo decodificó. Icecast 2.4.4 base reenvió los tres bloques. VLC no expuso la ficha. El código KH22 descarta ID3 en la ruta normal de streaming. No adoptarlo como salida principal. |
| AAC/ADTS con ICY | Título textual y, en variantes compatibles, campos o URL adicionales | Útil para compatibilidad. El código KH maneja `StreamTitle` y `StreamUrl`, con un bloque ICY limitado a 4.080 bytes de contenido. Una URL de imagen requiere que el receptor la interprete; no es la imagen incorporada del caso Ogg. |
| HLS Packed Audio AAC con ID3/APIC | Audio y metadatos temporizados dentro de segmentos, accesibles desde una lista | Validado en navegador con reproductor de prueba: dos portadas y vaciado durante la pausa. Es la mejor continuación para la web propia. |
| AAC en M4A/MP4 o HLS fMP4/MPEG-TS | Un archivo puede llevar portada; contenedores de streaming pueden llevar pistas o eventos de metadatos temporizados | Un M4A con portada de archivo no prueba actualizaciones en vivo. Son opciones de empaquetado para receptores concretos; no aportan compatibilidad automática a una app que solo acepta ADTS. No se implementaron en esta prueba. |
| SHOUTcast 2 con portada en su protocolo | Algunos emisores soportan enviar imágenes por canción al servidor SHOUTcast 2 | Documentado por proveedores de emisores. Requiere una cadena compatible, no es equivalente a Icecast/ICY corriente. No se comprobó y no hace falta cambiar el servidor actual para avanzar con HLS. |

FFmpeg documenta su opción ID3 al **inicio** de una salida ADTS. Su lector AAC también procesa etiquetas intermedias, pero el código de ese recorrido actualiza texto y no crea una nueva portada para cada etiqueta. Encontrar una imagen con `ffprobe` al abrir el flujo no equivale a ver su actualización en un reproductor.

## Ensayos reproducibles

Se generó audio sintético continuo y tres estados de MetaDATA: canción A con portada roja, canción B con portada azul, y pausa con artista/título/álbum vacíos y una imagen transparente. Se usaron los lectores y el empaquetador ID3/HLS que ya existen en el proyecto.

1. **AAC directo:** FFmpeg 9.0.1 reconoció el primer artista, título, álbum y PNG adjunto. Se insertaron tres bloques ID3 en límites de trama; el PCM decodificado con y sin etiquetas tuvo el mismo SHA-256. Eso demuestra que las etiquetas se pueden insertar sin cambiar el audio decodificado en este lector. No demuestra lo mismo en todos los clientes.
2. **Servidor Icecast base:** una conexión de fuente a Icecast 2.4.4 de laboratorio y un oyente HTTP. La captura contenía los tres bloques ID3 y los bytes de las dos imágenes originales. No se afirma copia íntegra del flujo: faltaron 1.159 bytes al final de la captura corta. Con el AAC etiquetado servido directamente por HTTP, VLC nativo mostró solo el nombre de recurso, sin artista, álbum ni portada. La prueba de VLC no dependía de Icecast ni de una API.
3. **Icecast-KH22:** el código de esta versión inicia sin la bandera `MPEG_KEEP_META`. El manejador descarta las etiquetas ID3 en ese modo. El lector de archivos con tamaño conocido activa esa bandera. Esta revisión del código explica la diferencia esperada frente al ensayo con Icecast 2.4.4 base.
4. **Navegador, lista terminada:** Chrome 156 y hls.js 1.7.4 reprodujeron 12,032 segundos. La página recibió A → B → pausa, comprobó los tres campos y reconstruyó las imágenes. Los hashes de las dos portadas coincidieron con sus originales.
5. **Navegador, lista que avanza:** el navegador se conectó cuando la lista estaba activa. La sesión reprodujo unos 24 segundos, solicitó la lista ocho veces y descargó doce segmentos. Mostró A y B con sus portadas originales, y ocultó la portada y vació los campos en la pausa. No hubo errores fatales ni solicitudes a Now Playing o a las imágenes originales. El final de la prueba cerró la lista; esto no es aún una prueba de 24/7, cortes de red ni reinicios.

La página del laboratorio interpreta nuestro ID3v2.4 y aplica los cambios en el tiempo de reproducción. Se utilizó Chrome sin ventana, con perfil temporal y sonido silenciado. No se validaron Safari, Firefox, Edge, móviles ni apps de radio ajenas. Apple y Android documentan APIs para recibir metadatos temporizados, pero sus apps deben usarlas y presentar las imágenes.

## Repetir la prueba en una computadora de desarrollo

Desde la raíz del repositorio, con Python y FFmpeg disponibles:

```text
python tools/research_aac.py
```

Esto genera archivos sintéticos en `work/aac-research`. Coloca ahí [hls.js 1.7.4](https://cdn.jsdelivr.net/npm/hls.js@1.7.4/dist/hls.min.js) como `hls.min.js`. SHA-256 de la copia ensayada: `cfc70cc9e9fc63d071919e087670abc760c8fd1bc889b88588026e4d22193bbe`. La librería no se incluye en el repositorio ni en la aplicación.

```text
python tools/research_aac.py --serve
```

Abre `http://127.0.0.1:18089/preview.html` y pulsa reproducir. Solo funciona en esa computadora. Para comprobar automáticamente los campos y portadas con Node.js 24 y Chrome, ejecuta `node tools/aac-chrome-proof.mjs`. En otras instalaciones, apunta `METADATA_TEST_CHROME` al ejecutable de Chrome; es solo un parámetro del laboratorio, no un ajuste necesario de MetaDATA. El resultado se guarda en `work/aac-research/chrome-hls.json`.

Para probar una lista que avanza, usa una subcarpeta nueva dentro del directorio servido con su copia de `hls.min.js`, y genera allí con `python tools/research_aac.py --live --directory work/aac-research/live`. Abre `/live/preview.html` inmediatamente al aparecer el aviso de lista lista; el primer título puede quedar fuera de la ventana si entras tarde. El generador utiliza segmentos de dos segundos en el laboratorio; la app actual usa seis.

## Próximo bloque de implementación

1. Integrar el lector de portada en el reproductor local de MetaDATA y verificar la salida del encoder que corre en Windows con audio real, cambios y pausas. Mantener AAC directo y MP3 como salidas separadas.
2. Preparar una publicación HTTPS autohospedada: subir cada segmento completo antes de anunciarlo en la lista, servir la lista sin caché prolongada y conservar los segmentos el tiempo necesario para los clientes activos. No publicar el servicio local directamente ni reintroducir conectores específicos de AzuraCast/Zeno en MetaDATA.
3. Limitar y optimizar las portadas sin perder la sincronía ni dejar al oyente que se incorpora a mitad de pista sin datos. Como referencia, repetir una imagen de 100 kB cada seis segundos añade unos 133 kbps, aproximadamente lo mismo que el audio de 128 kbps. Comprobar continuidad, búfer, cambios de canción, actualización de ficha, reconexión, seguridad de publicación y consumo antes de producción.
4. Validar por destino: usar HLS con ficha completa donde el receptor lo permita, AAC directo o MP3 donde solo se admita una URL de audio. La integración HLS del servidor y la lectura de portada en el reproductor web estándar de AzuraCast siguen pendientes.

## Fuentes primarias

- [RFC 8216: Packed Audio, timestamp ID3 PRIV y segmentos](https://www.rfc-editor.org/rfc/rfc8216.html#section-3.4).
- [ID3v2.4: APIC y campos de texto](https://id3.org/id3v2.4.0-frames), [estructura ID3v2.4](https://id3.org/id3v2.4.0-structure).
- [FFmpeg: salida ADTS](https://ffmpeg.org/ffmpeg-formats.html#adts), [lector AAC/ADTS](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/aacdec.c).
- [Icecast-KH: historial de cambios](https://github.com/karlheyes/icecast-kh/blob/icecast-2.4.0-kh22/NEWS), [tratamiento de ID3](https://github.com/karlheyes/icecast-kh/blob/icecast-2.4.0-kh22/src/mpeg.c#L560-L580), [ruta AAC/MPEG e ICY](https://github.com/karlheyes/icecast-kh/blob/icecast-2.4.0-kh22/src/format_mp3.c).
- [Apple: metadatos temporizados e imágenes en HLS](https://developer.apple.com/library/archive/documentation/NetworkingInternet/Conceptual/StreamingMediaGuide/UsingHTTPLiveStreaming/UsingHTTPLiveStreaming.html), [salida de metadatos AVPlayer](https://developer.apple.com/documentation/avfoundation/avplayeritemmetadataoutput).
- [hls.js: eventos de análisis de metadatos](https://hlsjs.video-dev.org/api-docs/hls.js.events), [Android Media3: extracción ID3 en HLS](https://developer.android.com/reference/androidx/media3/exoplayer/hls/HlsMediaSource.Factory).
- [Sound4: portadas mediante SHOUTcast 2](https://www.sound4helpdesk.com/metadata/metadata-scripts/).
