# Validación de entrega 0.3

## Entrega actual

Se aprobaron **46 pruebas** en macOS con Python 3.11 y PySide6 6.12.0. Se añadieron pruebas de claves separadas del JSON, lectura de claves guardadas por los conectores, prioridad sobre el entorno antiguo y borrado efectivo, separación por perfil/dirección, compensación ante fallos de guardado, migración v2, edición y cancelación en la interfaz, cuatro pantallas, cambio de tema y exportación de más de 200 filas de historial.

También se comprueba el vaciado de TXT/XML/JSON y salidas Icecast/AzuraCast durante pausas, con logo y mensaje separados de la canción; el respaldo de logo para canciones válidas sin portada; y el campo CASTTITLE del XML, formado durante canciones y vacío durante pausas. Las pruebas de conexiones usan GET/PROPFIND simulados, sin publicaciones. El reproductor se ejecutó en Node con un DOM simulado para canción, mensaje visual, logo y caducidad.

La interfaz se inspeccionó con capturas en modo offscreen y controles Fusion; esto no acredita la apariencia nativa en Windows. La versión 0.3 se construye como paquete Python. No se modificaron títulos, imágenes, ajustes ni bases de datos de la estación real.

El almacén Windows se prueba mediante un backend simulado, no con CredWrite nativo en este entorno. Quedan pendientes en Windows 11: persistencia entre arranques/EXE con el mismo usuario/perfil, mostrar/borrar claves, seguimiento del tema del sistema, bandeja, lectores nativos y tratamiento de XML/título vacío por RadioCaster. Icecast y AzuraCast requieren verificar el vaciado remoto y sus propios datos de respaldo; no se garantiza controlar el historial externo.

## Validación histórica 0.2


Fecha: 9 de noviembre de 2026. Entorno: macOS, Python 3.11, PySide6 6.12.0, httpx 0.28.1 y defusedxml 0.7.1 en un entorno aislado.

## Comprobaciones realizadas

La suite de 32 pruebas cubre selección/prioridad, exclusión de anuncios, carpetas, errores de fuente y XML malicioso; migración de configuración v1 con respaldo y de historial SQLite sin pérdida de filas; datos ampliados RadioBOSS y mapeo simulado de propiedades SMTC; exportaciones sin datos de anuncios ni rutas privadas; cambio a logo/mensaje por caducidad; Icecast-KH con falso éxito numérico y verificación de retorno por mount/título/URL; escritura AzuraCast limitada a campos admitidos; publicación WebDAV con imágenes antes que JSON, fallo de subida y retirada de la URL anterior; monitor estrictamente de lectura; demo sin conexiones externas; control de estación recibido durante una consulta de fuente; servidor local con rutas permitidas y bloqueo de configuración, rutas ajenas y Host no local.

La prueba de interfaz recorre datos ampliados, historial de seis columnas, ajustes de las nuevas conexiones, anuncios, conflicto y mensaje de estación, además del cierre ordenado del trabajador. La imagen de prueba se revisa visualmente.

El JavaScript del reproductor se ejecutó con un DOM simulado en Node: canción con álbum, mensaje/logo durante anuncio, caducidad con caída de actualizaciones y tratamiento de títulos como texto. No sustituye una prueba de audio real en un navegador Windows.

Las escrituras remotas se simulan con transportes HTTP locales. La compatibilidad WebDAV requiere comprobar tanto la carpeta de subida como la URL pública del alojamiento elegido.

Resultado final: **32 pruebas aprobadas**. Se construyó el paquete Python 0.2.0 correctamente.

## Pendientes en Windows 11 y servicios reales

- Lectura nativa WinRT/Spotify: estado, tipo, álbum, timeline y miniatura; las pruebas de mapeo no ejecutan WinRT nativo.
- RadioBOSS real: API, tipos, tags opcionales y carpetas Windows.
- Reemplazo continuo de archivos mientras RadioCaster los lee; bandeja y cierre de sesión de Windows.
- Una canción real a través del estudio: título, imagen remota y retardo frente al audio en cada destino.
- Autorización de escritura Icecast final o AzuraCast, sin otro escritor simultáneo; publicación StreamUrl y compatibilidad del reproductor.
- Subida WebDAV sobre el proveedor elegido y lectura pública de JSON/imágenes, MIME y caché.
- Construcción y arranque del EXE en una PC sin Python, empaquetado WinRT y firma.

Las pruebas de la versión 0.1 y el informe previo se conservan como contexto de la implementación incremental. Los datos de la consola física no se deducen de los metadatos y una clasificación musical no es una detección acústica de anuncios.

## Corrección Spotify 0.2.1

Se comprobó en los metadatos públicos de PyPI que los namespaces Foundation y Foundation.Collections no son dependencias automáticas de los paquetes Media 3.2.1 sin el extra `all`. Se agregaron explícitamente. Pasaron 17 pruebas de lógica, incluidas dos nuevas para informar el módulo WinRT faltante y evitar exponer mensajes de excepción ajenos. La descarga de las cinco bibliotecas WinRT y su runtime para CPython 3.11 Windows x64 se resolvió correctamente. Falta confirmar la ejecución nativa en la computadora Windows del usuario.
