# Publicación autohospedada

MetaDATA envía una ficha JSON y la portada juntas en una solicitud autenticada. El receptor conserva únicamente el estado actual, no una biblioteca creciente ni estadísticas de oyentes. No sustituye al servidor de audio. La futura página web queda fuera de este proyecto.

## Inicio con Docker Compose

Desde la raíz del repositorio, en el servidor con Docker Compose instalado:

```sh
docker compose -f receiver/compose.yaml build
docker compose -f receiver/compose.yaml run --rm receiver --init --host 0.0.0.0 --directory /data
```

La configuración y la clave se generan una sola vez en el volumen `config`; volver a inicializar no las sobrescribe. No necesitas editar las rutas para Docker.

Consulta la clave de `/config/receiver.json` de forma privada para introducirla en la app. No la pegues en tickets, capturas ni archivos del repositorio. El archivo no requiere variables de entorno.

```sh
docker compose -f receiver/compose.yaml up -d
```

El puerto del anfitrión se escucha solo en localhost. Publica ese puerto mediante tu proxy HTTPS, usando un subdominio propio cuya raíz apunte al receptor. Configura el proxy para limitar solicitudes a 6 MB y proteger la entrada con límites de frecuencia. El servidor Python está pensado para trabajar detrás de ese proxy, no como servidor TLS expuesto directamente. No cambies el servidor de audio.

Los volúmenes persisten tras actualizar el contenedor. `docker compose down -v` los elimina: no lo uses para actualizar. La imagen usa un usuario sin privilegios y no instala Qt ni FFmpeg. El Dockerfile está preparado; su construcción y despliegue deben comprobarse en el servidor de destino.

## Sin Docker

Solo requiere Python 3.11; el receptor usa la biblioteca estándar y no necesita instalar la interfaz gráfica:

```sh
python -m radio_metadata.receiver --config /ruta/privada/receiver.json --init
python -m radio_metadata.receiver --config /ruta/privada/receiver.json
```

Por defecto escucha en localhost y guarda una única instantánea en `./receiver-data/current.json`. Las rutas relativas se interpretan desde la carpeta de ejecución; usa una ruta absoluta en el servidor. Protege la configuración con permisos de lectura solo para la cuenta del servicio. En Windows usa los permisos de archivo del sistema para esa carpeta.

## En MetaDATA

En **Ajustes → Publicación** introduce la dirección HTTPS base y la clave. Pulsa **Probar conexión**: reconoce la clave sin publicar canciones. Activa el envío y guarda. Las claves quedan en el almacén de Windows.

La app publica al cambiar la canción, sus datos o su imagen. La posición transcurrida no dispara subidas de portada. Confirma vigencia aproximadamente cada 10 segundos por defecto; el intervalo se puede reducir y se procesa entre ciclos de consulta de fuentes. La consulta debe ser igual o más frecuente que ese intervalo. Usa un TTL con margen para las consultas y latencia; 45 segundos es el valor predeterminado. Si falla, reintenta con espera creciente hasta 30 segundos y publica el estado más reciente, sin una cola de canciones antiguas. Los cambios normales, incluidas las pausas, se envían sin esperar al siguiente latido; durante un fallo sigue aplicándose la espera del reintento. Al salir intenta enviar el vaciado.

El receptor caduca a los 45 segundos sin confirmación. Se puede ajustar `ttl` entre 15 y 300 segundos. La caducidad se aplica también después de reiniciar el receptor. La ficha y la imagen se guardan de forma atómica en un único archivo: la portada anterior deja de estar accesible al cambiar la canción. Solo se admite un publicador por receptor; no mezcles varias instancias con la misma clave.

## Contrato público

| Método / ruta | Uso |
| --- | --- |
| `GET /nowplaying.json` | Ficha pública: artista, título, álbum, género, identificadores disponibles y estado de vigencia. |
| `GET /artwork` | Portada actual; devuelve 204 si no existe o venció. |
| `GET /artwork/<hash>` | Portada de la revisión actual, indicada por `artwork_url` en el JSON. Un enlace anterior devuelve 404. |
| `GET /health` | Identificación pública del servicio. |
| `GET /api/v1/check` | Comprueba la clave sin modificar datos. |
| `PUT /api/v1/nowplaying` | Escritura autenticada de `{ "state": {...}, "artwork_base64": "..." }`. |
| `POST /api/v1/heartbeat` | Confirma la revisión actual; devuelve 409 si hay que reenviarla. |

Las escrituras y la comprobación usan `Authorization: Bearer <clave>`. Los datos públicos permiten consulta desde otras páginas mediante CORS. No se sirve el archivo de configuración ni rutas arbitrarias del disco. Se permiten imágenes PNG, JPEG o WebP de hasta 4 MB; la imagen se codifica en Base64 para enviarla dentro de la misma solicitud JSON. El cuerpo completo se limita a 6 MB.

El consumidor consulta el JSON, resuelve `artwork_url` respecto de la dirección del receptor y muestra la portada. En pausas, anuncios o caducidad: `is_music=false`, campos de canción vacíos e imagen ausente. El logo puede respaldar una canción real sin portada, pero nunca representa una pista ficticia. Los datos de identidad de la estación permanecen separados. Ninguna de estas rutas inserta carátulas en un flujo AAC/MP3 ni obliga a aplicaciones externas a leerlas.
