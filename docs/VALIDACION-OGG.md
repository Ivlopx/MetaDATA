# Validación de la copia experimental Ogg/Opus

Fecha: 10 de noviembre de 2026. Se usaron FFmpeg 9.0.1 con libopus, Icecast 2.4.4 instalado localmente y las bibliotecas nativas de VLC en macOS. El servidor de pruebas escuchó únicamente en loopback y se cerró al terminar. No se conectó a la estación ORO FM ni se cambiaron encoders, datos o ajustes remotos.

## Ensayo completo realizado

1. Se generó audio PCM sintético de 48 kHz y dos portadas PNG distintas.
2. La exportación real de MetaDATA generó JSON e imágenes en `covers` para canción A, pausa y canción B.
3. El módulo integrado `radio_metadata.ogg_encoder` recibió PCM por STDIN y siguió los cambios del JSON. Su salida se envió a un único socket SOURCE de Icecast.
4. VLC abrió la dirección del mount. Sin consultas de portadas a Internet, leyó artista, título y álbum de ambas canciones y extrajo las imágenes incorporadas.
5. Se compararon las imágenes extraídas con sus originales byte por byte.
6. Durante la pausa, VLC conservaba la portada anterior cuando simplemente no se enviaba imagen. La variante con una imagen transparente retiró visualmente la portada previa manteniendo artista, título y álbum vacíos.
7. El recuento de muestras decodificadas coincidió con las suministradas en la prueba original de 12 segundos: 576.000 muestras por canal. Esto no acredita por sí solo ausencia de fallos, calidad o sincronía en una emisión prolongada.

El módulo integrado repitió el recorrido completo después de reorganizar las imágenes en `covers`. La prueba real de FFmpeg de la suite también verifica entrada de 44,1 kHz, codificación Opus e imagen incorporada.

## Pruebas automatizadas y revisión visual

**65 pruebas aprobadas**, con las opciones de interfaz y FFmpeg activadas. La suite incluye lectura de metadatos, caducidad, pausas, rutas de imágenes contenidas en el perfil, imagen transparente, comprobación FFmpeg sin shell, comandos con espacios y marcadores RadioCaster, caché por historial visible, deduplicación, límites de espacio, protección de portada/logo, migración de imágenes, copia/apertura de rutas y estados de conexión basados en evidencia. Conserva las pruebas anteriores de selección, anuncios, credenciales, salidas e integraciones simuladas.

Las capturas de interfaz se revisaron con Qt/Fusion en modo offscreen; no acreditan la apariencia nativa Windows. Los iconos de Spotify, RadioBOSS y RadioCaster provienen de recursos oficiales. Los indicadores incluyen texto, distinguen fuente en pausa y ausencia de sesión, y no presentan la existencia del archivo de títulos como prueba de conexión del encoder.

## Límites de lo comprobado

No se ejecutó RadioCaster ni WinRT nativo en Windows. Falta verificar el comando dentro de Custom Encoders, la captura real y el comportamiento de reconexión de RadioCaster; el Icecast-KH de la instalación AzuraCast; receptores web y móviles; latencia, continuidad, consumo de CPU y memoria durante varias horas; y empaquetado del ayudante y FFmpeg para distribución Windows.

Se observan advertencias del demultiplexor FFmpeg al inspeccionar algunos Ogg encadenados, aunque el proceso termina correctamente y VLC lee los cambios. No se consideran una garantía de interoperabilidad con todos los decodificadores. Esta implementación concatena flujos lógicos Opus dentro de una misma conexión; esa capacidad es parte de lo que se debe comprobar en cada receptor.

La imagen transparente es un reemplazo explícito de limpieza: no equivale a ausencia de datos de imagen ni a una instrucción universal de borrar cachés. No se garantiza impedir entradas en historiales ajenos. Las imágenes dentro de Ogg no se importan automáticamente como portada de la API de AzuraCast.

## Fuentes técnicas

- [RadioCaster: codificadores externos](https://manual.djsoft.net/radiocaster/en/custom-encoders.html).
- [Liquidsoap: metadatos ICY y Ogg](https://www.liquidsoap.info/doc-2.3.0/icy_metadata.html).
- [Xiph: portadas en VorbisComment](https://wiki.xiph.org/VorbisComment#Cover_art).
- [AzuraCast: datos Now Playing](https://www.azuracast.com/docs/developers/now-playing-data/).
