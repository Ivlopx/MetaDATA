# Conectar con la estación

La demo y la interfaz no necesitan credenciales reales. Para la primera prueba en Windows se requieren estos datos **cuando se vaya a conectar**, no para probar el proyecto:

1. Versión de RadioBOSS y RadioCaster; URL/puerto de API local RadioBOSS y si usa usuario.
2. Carpetas reales de canciones y de anuncios/promos/jingles; nombres de tipos de archivo configurados en RadioBOSS.
3. Nombre, eslogan, web, descripción, mensajes y archivo de logo.
4. Confirmación del proveedor secundario: ¿es `zeno.fm` u otro dominio? Verificarlo en el panel del servicio.
5. Para la ruta recomendada, confirmar que los dos encoders ya conectan desde RadioCaster. No hacen falta sus claves dentro de esta app.
6. Solo si se elige escritura Icecast directa: URL base, mount exacto, nombre de usuario y qué variable de entorno local tendrá la contraseña. Para AzuraCast, confirmar primero que se trata de un endpoint Icecast administrativo autorizado y no de su entrada Liquidsoap DJ.

Introduce las claves en tu propia PC mediante variables de entorno. No las pegues en el repositorio ni en mensajes. RadioBOSS requiere contraseña en el query según su protocolo: usa localhost o HTTPS para acceso remoto. El proyecto no registra URLs ni mensajes de excepción de red que puedan incluirla. Los logs omiten títulos de anuncios y credenciales.

## Ruta recomendada

```text
RadioBOSS API ───────────────┐
                            ├─ selección → filtros → nowplaying.txt → RadioCaster
Spotify / Windows SMTC ─────┘                              ├─ AzuraCast
                                                           └─ destino secundario

                    imagen / logo → interfaz + archivos locales
```

El JSON incluye nombre/eslogan/descripción/web para un futuro reproductor propio. Esos campos no reconfiguran la ficha de estación de RadioCaster, AzuraCast o el proveedor secundario. Configura Station Info en RadioCaster y la identidad de la estación en cada panel por separado.

## Icecast directo opcional

Se configura en Ajustes → Salidas, como lista JSON. Empieza desactivado y reemplaza los valores de ejemplo:

```json
[
  {
    "name": "Icecast autorizado",
    "enabled": false,
    "url": "https://radio.example.org:8443",
    "mount": "/live.mp3",
    "username": "source",
    "password_env": "RADIO_ICECAST_PASSWORD"
  }
]
```

Define `$env:RADIO_ICECAST_PASSWORD` antes de iniciar la app. Usa HTTPS si está disponible; las credenciales Basic Auth sobre HTTP no se cifran. El servidor debe autorizar la actualización y tener el mount activo. La app comprueba la respuesta HTTP, `<return>1</return>` y un mensaje explícito de éxito de Icecast; una respuesta distinta se trata como error y se reintenta con espera creciente de hasta 60 segundos. Un cambio de título se envía sin esperar el refresco normal de 30 segundos, salvo que haya un error pendiente. Cada destino conserva su estado de reintento.

Si RadioCaster sigue enviando sus propios metadatos al mismo mount podría sobrescribir los de la app. Elige un solo escritor por destino. No actives esta opción por suposición para Zeno ni para el puerto de DJ de AzuraCast; utiliza primero la salida por RadioCaster.

## Comprobación en estudio

- Prueba fuera de emisión o en mount de prueba. Verifica acentos, guiones y cambios completos de canción.
- Reproduce una canción RadioBOSS de carpeta aprobada: confirmar título y carátula local si está etiquetada.
- Pausa RadioBOSS y reproduce Spotify: revisar sesión y estado local. Si solo se observa, debe seguir el mensaje de estación.
- Prueba ambas fuentes y cada prioridad; después pausa la fuente elegida manualmente. No debe saltar a la otra en modo manual.
- Activa Mensaje de estación **antes** de un bloque; confirma título remoto. Prueba además anuncios con artista/título y tipo Commercial: deben quedar fuera de archivo e historial.
- Pausa ambas, corta la API, restaura conexión y cierra/restaura la ventana. Verifica que el programa en bandeja siga trabajando.
- Cierra mediante Salir y confirma mensaje de estación. Si el proceso se mata o Windows corta energía, no hay garantía de limpieza del último título.
- Comprueba por separado el audio retornado por USB y los dos destinos remotos. Medir retardo de metadatos frente al audio; esta versión no lo compensa.

## Opciones nuevas en MetaDATA 0.2

### 1. Comprobación de lo que llega a ORO FM

En Ajustes → AzuraCast y monitoreo, activa «Comprobar título y estado». Ya se proponen:

- Panel: `https://orofm.live`
- Estación: `2`
- Servidor Icecast: `https://orofm.live:8000`
- Mount: `/vocesdetepezala/orofm/stream.mp3`

La pestaña «Lo que reciben los servidores» compara la última consulta con la selección. Una diferencia puede deberse a latencia, escritores simultáneos o una conexión mal elegida. El monitor no descarga ni sustituye la portada local: informa la URL que devuelve el servidor. Si cambia de canción, la marca de coincidencia puede variar antes de la siguiente consulta.

### 2. Vista local y lectura por URL

En Ajustes → Carátulas y reproductor activa la vista local. Por defecto utiliza:

```text
http://127.0.0.1:12882/player.html
http://127.0.0.1:12882/nowplaying.txt
http://127.0.0.1:12882/nowplaying.json
http://127.0.0.1:12882/nowplaying.xml
```

En RadioCaster puedes seguir leyendo el archivo o usar «Read from URL» con la URL TXT. Si el servicio se cierra, RadioCaster puede conservar el último texto recibido: compruébalo. No se abre un puerto para Internet ni se configura el router. El reproductor requiere una acción del usuario para escuchar el audio.

Para leer el XML en RadioCaster con primera versión de salida textual, usa `{TRACK[TITLE]}`: en una canción solo mostrará el título. Para conservar el texto combinado y el mensaje de estación sin separadores vacíos, usa TXT. Los atributos del XML están disponibles para plantillas, pero no se presupone que el servidor los reciba como campos independientes.

### 3. Carátula exacta en Internet mediante alojamiento compatible

Se necesita una **carpeta WebDAV existente por HTTPS**, con permisos de PUT, y una **URL pública** desde la cual se puedan consultar los archivos subidos. Una instalación Nextcloud privada o el dominio de AzuraCast por sí solos no garantizan esas dos condiciones. La carpeta de destino debe existir; la app no crea cuentas ni carpetas remotas.

Configura ambos destinos en Ajustes → Carátulas y reproductor. Define antes de iniciar:

```powershell
$env:METADATA_WEBDAV_PASSWORD = 'tu contraseña de aplicación del alojamiento'
```

La app sube `player.html`, `nowplaying.json`, `nowplaying.txt` e imágenes PNG/JPEG/WebP de hasta 4 MB. El JSON no incluye rutas locales ni anuncios excluidos. Abre la URL pública `/player.html` para ver la canción. El álbum se conserva en JSON, no se añade al título de radio. Configura en el alojamiento que JSON no se almacene en caché de larga duración; las imágenes llevan nombres diferentes por contenido. El envío mantiene el JSON actualizado aproximadamente cada 10 segundos; el reproductor oculta la música si supera su caducidad configurada.

El alojamiento debe servir HTML/JSON e imágenes con los tipos adecuados. Si subida y lectura pública corresponden a lugares diferentes, corrige esas URLs antes de usar StreamUrl. La publicación remota conserva archivos de imágenes para no romper lectores; define una política de limpieza de archivos antiguos en el alojamiento.

Protocolo utilizado: PUT de archivos sobre HTTPS, documentado por [Nextcloud/WebDAV](https://docs.nextcloud.com/server/latest/developer_manual/client_apis/WebDAV/basic.html). No se presupone compatibilidad de un proveedor que no admita este protocolo.

### 4. StreamUrl en Icecast-KH

Después de verificar la publicación de imágenes, un destino directo puede incluir:

```json
[
  {
    "name": "Icecast-KH de prueba",
    "enabled": false,
    "url": "https://orofm.live:8000",
    "mount": "/vocesdetepezala/orofm/stream.mp3",
    "username": "source",
    "password_env": "RADIO_ICECAST_PASSWORD",
    "send_artwork_url": true,
    "verify_url": "https://orofm.live:8000/status-json.xsl"
  }
]
```

No actives este ejemplo con credenciales de entrada DJ Liquidsoap por suposición. Requiere acceso de actualización al Icecast final y coordinar que RadioCaster/Liquidsoap no sobrescriban el dato. Sin alojamiento activo la configuración rechaza StreamUrl. Si falla la nueva imagen, se envía URL vacía para no reutilizar la canción anterior; el reproductor externo podría conservar su propia caché.

Una respuesta KH debe indicar éxito en código y mensaje. Si está configurado `verify_url`, la app comprueba después la salida publicada; la respuesta podría adelantarse al cambio visible y causar un reintento. Una escritura aceptada sin lectura se etiqueta expresamente como aún sin verificar. No se considera la URL de portada una imagen embebida en Icecast, ni se supone que modifique `song.art` de AzuraCast.

### 5. Actualización textual directa en AzuraCast

Alternativa al título enviado por RadioCaster: habilitar «Publicar artista y título directamente por AzuraCast», con clave de una cuenta autorizada para Broadcasting. Define localmente:

```powershell
$env:AZURACAST_API_KEY = 'tu clave API local'
```

Se usa POST a `/api/station/2/nowplaying/update`, con `artist`/`title` únicamente y la clave en cabecera. No se envían álbum, imagen, duración artificial ni referencias a archivos de la biblioteca. Las canciones excluidas envían artista vacío y mensaje de estación como título. El panel puede confirmar recepción antes de que el cambio aparezca públicamente; el monitor muestra el resultado después.

La app impide activar simultáneamente su escritura Icecast y su escritura AzuraCast. También debes elegir quién envía títulos desde RadioCaster; la app no puede desactivar ese ajuste por ti. Verifica en una estación de prueba antes de usar una ruta nueva.

### 6. Funciones que se configuran en los programas originales

La búsqueda de carátulas se activa con permisos de administrador en los servicios de AzuraCast. AutoDJ de respaldo, grabaciones, varias calidades y relay secundario siguen en su panel. El programador y la captura USB siguen en RadioCaster. La adaptación no instala componentes del servidor ni cambia tu transmisión actual.
