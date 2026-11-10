# AAC principal, MP3 de respaldo y prueba HLS con portada

Versión 0.4.0a2, 10 de noviembre de 2026. AAC es la ruta principal del proyecto; MP3 queda como respaldo. La salida Ogg sigue disponible para VLC y otros receptores compatibles.

## Qué está implementado

- Un codificador de consola recibe PCM s16le de RadioCaster y devuelve AAC-LC/ADTS o MP3 por STDOUT. RadioCaster conserva captura y conexión. La misma instalación admite ambas salidas en conexiones separadas; no hay conmutación automática del oyente entre ellas.
- Ajustes → **Codificador** permite elegir AAC, MP3 u Ogg, comprobar FFmpeg y copiar comando y MIME. AAC usa `audio/aac`, MP3 `audio/mpeg`, Ogg `audio/ogg`. Los comandos nuevos no alteran las conexiones ya guardadas en RadioCaster.
- Se intenta obtener automáticamente la ruta abreviada de Python en Windows, para evitar el fallo observado con una ruta de ejecutable con espacios en RadioCaster 3.7. Si Windows no ofrece un nombre corto, la app muestra una explicación: hace falta reinstalar Python y el entorno en rutas sin espacios, no mover un entorno virtual existente. Las rutas que son argumentos, como JSON y FFmpeg, conservan comillas cuando las necesitan.
- Opción **Generar también HLS local con portada**: solo para AAC, además de la salida directa genera `output/hls/live.m3u8` y segmentos AAC de unos seis segundos. No cambia la salida STDOUT de RadioCaster.

**El AAC/MP3 directo no lleva portadas dinámicas.** Se conserva así para la compatibilidad ordinaria de las conexiones Icecast. Los archivos TXT/XML/JSON y la actualización de título de RadioCaster siguen disponibles por separado. No se deben confundir el archivo AAC/MP3, las etiquetas de una transmisión y lo que muestra cada aplicación.

## Actualizar la copia existente

Cierra MetaDATA desde **Salir** y, dentro de la carpeta del repositorio, ejecuta:

```powershell
git pull --ff-only
.\instalar.bat
.\iniciar.bat
```

Se conserva el perfil `%LOCALAPPDATA%\RadioMetadataManager-OggPrueba`. Los ajustes AAC nuevos tienen valores predeterminados y no cambian los del servidor. No hace falta crear otra instalación.

## Prueba AAC directa

1. Ajustes → Codificador → **AAC — Principal**.
2. Selecciona tu `ffmpeg.exe`, pulsa **Comprobar codificador** y guarda. Mantén HLS desactivado si solo quieres probar audio.
3. Copia el comando para RadioCaster; crea un Custom Encoder llamado `MetaDATA AAC` y MIME `audio/aac`.
4. Usa una conexión de prueba independiente de la transmisión actual: 128 kbps, estéreo, 44,1 o 48 kHz. El destino debe admitir AAC. Para Icecast directo, usa su puerto, usuario y contraseña de fuente y un punto de montaje dedicado, con AutoDJ desactivado únicamente en ese mount. La entrada de DJs de Liquidsoap vuelve a codificar al formato de salida configurado; no preserva sin más los metadatos incorporados.
5. Comprueba el audio con VLC y los reproductores de destino. La compatibilidad todavía debe probarse en cada uno.

Para MP3, selecciona **MP3 — Respaldo**, copia otro comando y crea `MetaDATA MP3`, MIME `audio/mpeg`. Usa una conexión propia. Seleccionar MP3 no elimina ni convierte la salida AAC, ni activa una selección automática de reserva en las apps.

## Prueba local de AAC con portada mediante HLS

1. Selecciona AAC y activa **Generar también HLS local con portada**, guarda y vuelve a copiar el comando de RadioCaster. Solo una conexión debe generar HLS en ese perfil: un bloqueo impide dos escritores simultáneos.
2. Habilita el servidor local desde Ajustes → Carátulas. RadioCaster debe estar suministrando audio al comando para que aparezcan los archivos HLS. No apuntes dos conexiones HLS al mismo perfil.
3. Con el puerto predeterminado, la lista local está en `http://127.0.0.1:12882/hls/live.m3u8`. Puedes probarla en VLC; esa URL es solo de la computadora donde corre MetaDATA. El reproductor HTML incluido sigue usando la URL de audio configurada y el JSON; no incorpora todavía un lector HLS/ID3/APIC específico.
4. Espera a que se generen varios segmentos. Cambia entre dos canciones con portadas distintas y después pausa los metadatos. Cada segmento nuevo toma una instantánea: los datos pueden tardar unos seis segundos en entrar en un segmento, más el búfer del cliente.
5. Los segmentos llevan título, artista, álbum, artista del álbum, género, año y PNG/JPEG. Para pausas, anuncios y datos vencidos, los campos de canción quedan vacíos y se incluye una imagen transparente. No se publica el nombre de la estación como canción. Una canción sin imagen usa la portada/logo que haya exportado MetaDATA, o imagen transparente.

Los archivos de HLS usan **Packed Audio** con timestamp PRIV de 90 kHz e ID3v2.4/APIC. Las imágenes van en los segmentos, no en la salida AAC directa de RadioCaster. Se retienen seis segmentos en la lista y un margen adicional para clientes que siguen descargando: el almacenamiento es acotado y los anteriores se limpian al avanzar. Su ocupación es independiente del límite de `covers`; una portada grande se repite por segmento. No es una medición de rendimiento de larga duración.

## Lo que falta para una salida pública

Esta versión genera y sirve HLS solo en la computadora local. **No publica ni sube los segmentos HLS al servidor de ORO FM**, ni modifica los puertos de Icecast o las opciones HLS de AzuraCast. El WebDAV existente publica Now Playing y sus imágenes, no esta secuencia de segmentos y listas.

Publicar HLS requiere alojamiento HTTP/HTTPS que preserve las listas y segmentos, y un reproductor que extraiga ID3/APIC y actualice su interfaz. Que un navegador o app pueda reproducir AAC no acredita que lea HLS o muestre su portada. Tampoco se actualiza automáticamente `song.art` de AzuraCast. Antes de producción faltan publicación continua, reproducción en navegadores, actualización de imágenes, pausas, reconexiones y pruebas prolongadas.

No detengas el MP3 existente para comprobar HLS. El objetivo sigue siendo que el oyente pulse una sola vez; las diferencias de empaquetado e interpretación pertenecen a la integración del reproductor.

## Validación realizada

**71 pruebas aprobadas**, con interfaz Qt, Ogg y AAC reales activados. AAC y MP3 se decodifican; HLS generado se abre con el demultiplexor HLS de FFmpeg; las etiquetas de título y portada de cada segmento se reconocen. Pruebas de estructura: imágenes, Unicode, timestamp de 33 bits, cambios de canción, vaciado, lista deslizante, conservación temporal de segmentos retirados y bloqueo de escritores. Los ensayos de fragmentación verifican que el parser admite tramas ADTS divididas entre lecturas. También se verifican los tipos MIME y el acceso HTTP local solo a los archivos HLS previstos. Estas pruebas no equivalen a validación de Safari/Chrome/Edge/Firefox ni de Windows/RadioCaster para el módulo AAC nuevo.

## Referencias

- [RFC 8216, sección 3.4: Packed Audio y timestamp ID3 PRIV](https://www.rfc-editor.org/rfc/rfc8216.html#section-3.4).
- [ID3v2.4: APIC y campos de canción](https://id3.org/id3v2.4.0-frames).
- [Estructura ID3v2.4 y tamaños synchsafe](https://id3.org/id3v2.4.0-structure).
- [FFmpeg: formatos ADTS y MP3](https://ffmpeg.org/ffmpeg-formats.html).
- [Apple: metadatos sincronizados e imágenes en HLS](https://developer.apple.com/library/archive/documentation/NetworkingInternet/Conceptual/StreamingMediaGuide/UsingHTTPLiveStreaming/UsingHTTPLiveStreaming.html).
- [RadioCaster: contrato de codificadores externos](https://manual.djsoft.net/radiocaster/en/custom-encoders.html).
