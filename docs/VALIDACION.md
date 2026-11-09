# Validación de entrega 0.2

Fecha: 9 de noviembre de 2026. Entorno: macOS, Python 3.11, PySide6 6.12.0, httpx 0.28.1 y defusedxml 0.7.1 en un entorno aislado.

## Comprobaciones realizadas

La suite de 32 pruebas cubre selección/prioridad, exclusión de anuncios, carpetas, errores de fuente y XML malicioso; migración de configuración v1 con respaldo y de historial SQLite sin pérdida de filas; datos ampliados RadioBOSS y mapeo simulado de propiedades SMTC; exportaciones sin datos de anuncios ni rutas privadas; cambio a logo/mensaje por caducidad; Icecast-KH con falso éxito numérico y verificación de retorno por mount/título/URL; escritura AzuraCast limitada a campos admitidos; publicación WebDAV con imágenes antes que JSON, fallo de subida y retirada de la URL anterior; monitor estrictamente de lectura; demo sin conexiones externas; control de estación recibido durante una consulta de fuente; servidor local con rutas permitidas y bloqueo de configuración, rutas ajenas y Host no local.

La prueba de interfaz recorre datos ampliados, historial de seis columnas, ajustes de las nuevas conexiones, anuncios, conflicto y mensaje de estación, además del cierre ordenado del trabajador. La imagen de prueba se revisa visualmente.

El JavaScript del reproductor se ejecutó con un DOM simulado en Node: canción con álbum, mensaje/logo durante anuncio, caducidad con caída de actualizaciones y tratamiento de títulos como texto. No sustituye una prueba de audio real en un navegador Windows.

Las escrituras remotas se simulan con transportes HTTP locales. No se publicaron títulos, imágenes ni ajustes en ORO FM durante las pruebas. La compatibilidad WebDAV requiere comprobar tanto la carpeta de subida como la URL pública del alojamiento elegido.

Resultado final: **32 pruebas aprobadas**. Se construyó el paquete Python 0.2.0 correctamente. Además, el monitor nuevo realizó consultas reales de lectura a ORO FM: AzuraCast e Icecast estaban online y coincidían con el mensaje de estación esperado. Esto valida la lectura, no la publicación de una canción ni la sincronía con el audio.

## Pendientes en Windows 11 y servicios reales

- Lectura nativa WinRT/Spotify: estado, tipo, álbum, timeline y miniatura; las pruebas de mapeo no ejecutan WinRT nativo.
- RadioBOSS real: API, tipos, tags opcionales y carpetas Windows.
- Reemplazo continuo de archivos mientras RadioCaster los lee; bandeja y cierre de sesión de Windows.
- Una canción real a través del estudio: título, imagen remota y retardo frente al audio en cada destino.
- Autorización de escritura Icecast final o AzuraCast, sin otro escritor simultáneo; publicación StreamUrl y compatibilidad del reproductor.
- Subida WebDAV sobre el proveedor elegido y lectura pública de JSON/imágenes, MIME y caché.
- Construcción y arranque del EXE en una PC sin Python, empaquetado WinRT y firma.

Las pruebas de la versión 0.1 y el informe previo se conservan como contexto de la implementación incremental. Los datos de la consola física no se deducen de los metadatos y una clasificación musical no es una detección acústica de anuncios.
