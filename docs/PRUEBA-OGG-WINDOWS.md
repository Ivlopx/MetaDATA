# Prueba de Ogg/Opus con portadas en RadioCaster

**Guía de Ogg/Opus experimental.** Desde 0.4.0a2 el formato principal es AAC, con MP3 de respaldo: [guía AAC/HLS](PRUEBA-AAC-WINDOWS.md). Ogg continúa disponible. Esta copia conserva RadioCaster para capturar el audio y mantener la conexión. Un codificador externo recibe ese audio, lee el JSON local de MetaDATA y devuelve una señal Ogg/Opus con artista, título, álbum y portada incorporados.

La prueba de laboratorio pasó con Icecast 2.4.4 y VLC en macOS, usando audio sintético y una sola conexión de emisión. **Todavía no se ha validado dentro de RadioCaster en Windows ni en el Icecast-KH.** No se modificó la emisión real.

## Mantener separada la versión estable

Clona la rama de prueba en una carpeta nueva, sin reutilizar la carpeta de tu instalación estable:

```powershell
git clone https://github.com/Ivlopx/MetaDATA.git MetaDATA-PruebaOgg
cd MetaDATA-PruebaOgg
.\instalar.bat
.\demo.bat
```

También puedes descomprimir el ZIP de esta versión en una carpeta nueva y ejecutar esos dos archivos BAT. El ZIP contiene el proyecto Python, no un EXE Windows ya construido.

La carpeta de datos predeterminada de esta rama es:

```text
%LOCALAPPDATA%\RadioMetadataManager-OggPrueba
```

La estable conserva `%LOCALAPPDATA%\RadioMetadataManager`. No uses `--data-dir` para apuntar la prueba al perfil estable. Las claves se separan por perfil; hay que introducirlas en los formularios de esta copia. No es necesario copiar credenciales de transmisión a MetaDATA para usar el codificador: siguen en RadioCaster.

## Preparar FFmpeg

Necesitas una compilación Windows x64 de **FFmpeg con libopus**. La página del proyecto enlaza los proveedores de binarios Windows: [descargas de FFmpeg](https://ffmpeg.org/download.html#build-windows).

1. Descomprime FFmpeg en una carpeta fija, por ejemplo dentro de esta copia de prueba. No requiere definir variables de entorno.
2. Abre MetaDATA → Ajustes → **Codificador** y selecciona **Ogg/Opus — Experimental**.
3. Pulsa **Elegir FFmpeg** y selecciona `ffmpeg.exe` en su carpeta `bin`.
4. Pulsa **Comprobar codificador**. Solo verifica el programa y libopus: no emite audio ni cambia RadioCaster.
5. Guarda y vuelve a la sección para pulsar **Copiar comando para RadioCaster**.

No se distribuyen binarios FFmpeg dentro del ZIP. Si se prepara un instalador futuro habrá que incluir sus licencias y verificar la compilación concreta. Esta prueba utiliza la instalación Python; un EXE gráfico creado con `--windowed` no sirve para enviar audio binario por la consola.

## Configurar un destino de prueba en RadioCaster

Usa un mount o estación de prueba autorizado, separado de la emisión actual. **No cambies el archivo global de metadatos de RadioCaster que usa tu emisión estable.** El complemento lee por su cuenta el JSON de esta copia de MetaDATA.

1. En RadioCaster abre **RadioCaster → Custom Encoders**.
2. Agrega un codificador llamado, por ejemplo, `MetaDATA Ogg (prueba)`.
3. Pega el comando copiado desde la app. Conserva los marcadores `{SampleRate}`, `{Channels}` y `{Bitrate}`: RadioCaster los sustituye por los valores del encoder.
4. En el tipo MIME indica `audio/ogg`.
5. Agrega una conexión nueva hacia el destino de prueba y selecciona este codificador, con 128 kbps y mono o estéreo. No reemplaces el encoder MP3/AAC que ya funciona al aire.
6. Abre la dirección de ese mount en un reproductor compatible con metadatos Ogg/Opus, como VLC, y comprueba los datos.

El contrato de entrada/salida está [documentado por DJSoft](https://manual.djsoft.net/radiocaster/en/custom-encoders.html): audio PCM de 16 bits con signo, little-endian, por STDIN; señal codificada por STDOUT. Esta implementación admite mono/estéreo, varias frecuencias de entrada, incluida 44,1 kHz, y codifica Opus a 48 kHz.

## Comprobar antes de pensar en producción

- Reproduce dos canciones con portadas distintas: deben cambiar artista, título, álbum e imagen sin reconectar manualmente al oyente.
- Activa **Pausar metadatos** en la copia de prueba. Artista, título y álbum deben quedar vacíos. Una imagen transparente sustituye la portada anterior para evitar que VLC la retenga; no se envían el nombre ni el eslogan de la estación como canción.
- Reanuda y prueba una canción sin imagen. Se utilizará el logo si está configurado y exportado; de lo contrario se usa la imagen transparente para retirar la anterior.
- Prueba cierre del ayudante, datos caducados, interrupción y reconexión, y escucha continuidad y latencia durante varias canciones.
- Prueba los reproductores de destino: algunos reproducen Opus pero no muestran sus metadatos o no actualizan la imagen.

En esta versión el complemento incorpora imágenes **PNG y JPEG**. Si recibe una imagen no admitida, por ejemplo WebP, la sustituye por la imagen transparente en vez de conservar una portada de otra canción. La prueba no está lista para sustituir una emisión en producción sin validación nativa y de larga duración.

## Qué resuelve y qué permanece aparte

La información de Spotify/RadioBOSS sigue procediendo de sus lectores de MetaDATA. La consola únicamente aporta audio. La selección por reproducción y prioridad no confirma qué señal está pasando por la consola.

Esta salida entrega la imagen dentro del flujo a receptores compatibles. **No modifica automáticamente `song.art` de la API de AzuraCast, ni hace que su reproductor web integrado lea esas imágenes del audio.** Su reproductor obtiene el audio y la ficha Now Playing por vías distintas. La búsqueda Last.fm y el alojamiento JSON/WebDAV continúan siendo alternativas separadas.

La señal MP3/AAC existente y los archivos **TXT, XML y JSON** siguen disponibles. En Inicio y Conexiones → RadioCaster puedes seleccionar el formato, copiar la ruta y abrir la carpeta. No se presupone que todos los otros encoders lean exactamente la misma plantilla XML; TXT sigue siendo la alternativa de título combinado.

## Portadas e historial

Las imágenes locales se guardan en `output/covers` o `demo-output/covers`. Los archivos antiguos con los nombres y hashes propios de la app se reorganizan al publicar; otros archivos personales no se mueven.

En Ajustes → Música puedes definir las canciones visibles (10–1000, inicialmente 200) y el espacio de portadas (8–4096 MB, inicialmente 128). Se conservan las imágenes de esas canciones, deduplicadas, y se protegen la portada y el logo actuales. Si no caben todas, se retiran las menos recientes. El historial SQLite de texto se conserva; no se convierte esta acción en una eliminación de registros ni en un sistema nuevo de informes.

Estos límites son **locales**. No borran imágenes remotas. En WebDAV la app crea o comprueba la subcarpeta `covers` y mantiene los enlaces de los archivos publicados; el servidor necesita una política de retención propia para imágenes remotas antiguas.

## Volver a la versión estable

Detén únicamente la conexión de prueba de RadioCaster y cierra MetaDATA Prueba Ogg desde Salir. La instalación, el perfil y la conexión estable permanecen separados. Si has cambiado manualmente algún encoder u origen global de metadatos, restáuralo con los valores que anotaste antes de la prueba.
