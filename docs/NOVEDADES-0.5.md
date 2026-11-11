# MetaDATA 0.5.0a1

## Fuentes y prioridad

En Ajustes → Fuentes se detectan las sesiones multimedia activas de Windows. Cada fuente adicional tiene permisos independientes para consultar y publicar, y se puede subir o bajar en la prioridad. Las fuentes nuevas permanecen desactivadas. No se garantiza que toda aplicación instalada exponga datos mediante Windows; no se afirma que una sesión sea la señal al aire.

RadioBOSS conserva su API específica. Spotify conserva la identificación existente. Las fuentes adicionales se identifican por la sesión exacta para evitar coincidencias entre aplicaciones; varias sesiones reproduciendo simultáneamente se rechazan. La clasificación musical desconocida requiere autorización explícita. Se siguen exigiendo artista y título válidos y aplicando exclusiones.

## Reglas de carpetas

Lista blanca y negra con selección de carpetas y casilla Incluir subcarpetas por regla. La lista negra prevalece. Las carpetas anteriores mantienen su comportamiento recursivo; guardar o cancelar no modifica archivos de música. Solo RadioBOSS aporta aquí la ruta local del archivo: no se inventan rutas para fuentes multimedia de Windows.

## Estación

Nombre, descripción, sitio web, género, logo y tema en el primer nivel. Eslogan y mensajes visuales quedan en una sección desplegable opcional. Los datos de la estación siguen separados de las canciones.

## Publicación

Receptor autohospedado con clave guardada desde la app, envío conjunto de JSON e imagen, confirmaciones periódicas, reintentos del estado más reciente, vaciado en pausas y caducidad automática. Guarda una única instantánea e imagen actual, sin crecimiento de biblioteca. Servicio Python sin dependencias externas y configuración Docker Compose: [guía del receptor](RECEPTOR.md).

Las salidas Now Playing TXT/XML/JSON, AAC, MP3, HLS y Ogg existentes permanecen disponibles. No se reintroducen conexiones directas a proveedores de emisión.

## Validación y pendientes

84 pruebas locales: reglas recursivas, prioridades y anuncios, detección y lectura SMTC simulada, guardado y cancelación de ajustes, privacidad de claves, HTTP del receptor, portada exacta, pausa, caducidad y reintentos, además de los encoders existentes. Se revisaron visualmente Fuentes y Reglas y se validó la configuración Compose. El servicio Docker no estaba iniciado en el equipo de desarrollo, por lo que no se construyó ni ejecutó el contenedor.

Pendientes: detección nativa en Windows con cada reproductor elegido, despliegue HTTPS del receptor y comprobación del contenedor en el servidor de destino. El monitoreo de audio/silencio, incidentes, estadísticas de oyentes e instalador final con FFmpeg siguen en etapas posteriores.
