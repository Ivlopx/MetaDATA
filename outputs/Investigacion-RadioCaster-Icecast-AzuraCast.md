# RadioCaster, Icecast y AzuraCast: posibilidades para MetaDATA y ORO FM

Investigación y consultas públicas: **9 de noviembre de 2026**. Alcance: metadatos, carátulas, publicación, monitoreo y funciones de emisión relacionadas con el proyecto. Las capacidades del proveedor se distinguen de lo que MetaDATA ya implementa. No se inició sesión ni se cambió la emisión.

> Informe de investigación previo a la versión 0.2. La adaptación posterior se describe en [Novedades 0.2](../docs/NOVEDADES-0.2.md). El defecto de validación KH señalado en este informe quedó corregido; los nuevos conectores y sus límites están documentados allí.

## 1. Resultado principal

Podemos mantener RadioCaster para el audio y el título convencional, usar la búsqueda de portadas de AzuraCast y desarrollar una salida adicional para datos completos e imágenes propias. **No hay evidencia de que la lectura normal de XML de RadioCaster entregue álbum, año e imagen como campos independientes a toda la cadena.** Tampoco basta con mandar `album` o `art` al endpoint de actualización de AzuraCast: las versiones examinadas filtran esos campos. [RadioCaster: metadatos](https://manual.djsoft.net/radiocaster/en/metadata.html), [AzuraCast 0.20.2: filtro de actualización](https://github.com/AzuraCast/AzuraCast/blob/0.20.2/backend/src/Controller/Api/Stations/UpdateMetadataAction.php).

Eso explica que otras estaciones sí muestren portadas: pueden obtenerlas mediante búsquedas externas, la biblioteca del AutoDJ o una integración propia. Mostrar imágenes en una web y transportarlas mediante el stream son mecanismos diferentes. [Resolución de carátulas de AzuraCast](https://github.com/AzuraCast/AzuraCast/blob/0.20.2/backend/src/Entity/ApiGenerator/SongApiGenerator.php).

## 2. Qué se pudo observar en tu instalación

| Dato | Resultado público observado |
| --- | --- |
| Dominio | `https://orofm.live`; la raíz redirige al inicio de sesión de AzuraCast |
| Estación | ORO FM 88.1; ID 2; identificador `on-air` |
| Estado en la consulta | Online; AzuraCast reportaba `live.is_live=false` |
| Salida anunciada | MP3, 320 kbps; mount `/vocesdetepezala/orofm/stream.mp3` |
| Título en la consulta | ORO FM 88.1 - ¡Una radio que sí brilla! |
| Datos de canción | Álbum, género, ISRC y letra vacíos; `song.art` apuntaba a una imagen de estación |
| Icecast identificado | `Icecast 2.4.0-kh22`, según sus estadísticas públicas |
| Versión declarada por la documentación API | AzuraCast 0.20.2; no es una inspección del servidor instalado |
| RadioCaster | El usuario indica la última versión. La publicación oficial consultada anuncia RadioCaster 3.7; no se inspeccionó el ejecutable de Windows |

Evidencia: [Now Playing público](https://orofm.live/api/nowplaying), [OpenAPI de la instalación](https://orofm.live/api/openapi.yml), [estado público Icecast](https://orofm.live:8000/status-json.xsl), [anuncio RadioCaster 3.7](https://www.djsoft.net/enu/news/183.htm). Son consultas puntuales: el contenido y el estado pueden cambiar. No se deduce de `is_live=false` cómo están conectados tus encoders, ni de la imagen de respaldo que la búsqueda externa esté desactivada. Faltó observar una canción real para comprobarlo.

Se contrastó el código etiquetado **0.20.2**, correspondiente a la versión declarada por tu API, con **0.23.9** y la revisión de desarrollo `276b9d289dc4e0caf2ab575247527a6a81062a0f`. Las limitaciones descritas no se basan solamente en versiones nuevas.

## 3. RadioCaster: lo que aporta y sus límites

### Metadatos

Su manual permite leer el nombre de pista desde texto fijo, archivo, URL, XML o un stream retransmitido. En XML puede combinar nodos y atributos en una plantilla. Por ejemplo, añadir `{TRACK[ALBUM]}` permite incorporar el álbum al **texto resultante**; no demuestra que lo envíe como una etiqueta ALBUM independiente. [Manual de metadatos](https://manual.djsoft.net/radiocaster/en/metadata.html).

Las reglas de posprocesamiento pueden modificar títulos o impedir su envío. Son una segunda protección útil, pero omitir una actualización podría dejar visible el título anterior: MetaDATA debe generar el mensaje de estación de forma explícita durante el bloque. [Posprocesamiento](https://manual.djsoft.net/radiocaster/en/metadata-postprocess.html).

No encontré en la documentación examinada una interfaz de envío de carátula dinámica por canción ni una API pública de control remoto equiparable a la de RadioBOSS. Se trata de una capacidad **no verificada**, no de una afirmación de imposibilidad. El ajuste StreamURL documentado para **RadioBOSS** no se debe atribuir a RadioCaster.

### Audio y operación

Puede capturar entrada de sonido o reproducción de Windows y retransmitir una fuente de red; soporta varios formatos y servidores compatibles con Icecast/Shoutcast. Incluye procesamiento DSP y admite plugins VST/Winamp. Sus encoders permiten elegir formato, bitrate y datos de estación por conexión. Esto permite conservar la captura del retorno USB de tu consola. [Producto](https://www.djsoft.net/enu/radiocaster_details.htm), [fuentes de audio](https://manual.djsoft.net/radiocaster/en/sources.html), [encoders](https://manual.djsoft.net/radiocaster/en/setting-up-encoders.html).

También hay programación de inicio/parada de emisión, estadísticas que pueden consultarse desde otro servidor y encoders personalizados; la opción RTMP permite una imagen o vídeo de fondo mediante el plugin correspondiente. RTMP es otra salida de emisión: no convierte esa imagen en portada dinámica del stream Icecast. [Programador](https://manual.djsoft.net/radiocaster/en/scheduler.html), [estadísticas](https://manual.djsoft.net/radiocaster/en/statistic-relays.html), [RTMP](https://manual.djsoft.net/radiocaster/en/rtmp-streaming.html).

## 4. Icecast: transporte, estadísticas y variante KH

La ruta administrativa documentada actualiza un mount activo mediante `/admin/metadata`, `mode=updinfo` y `song`. Se autentica con credenciales autorizadas para ese mount o de administración. Sirve para publicar título o mensaje de estación desde un programa externo. [Interfaz administrativa](https://www.icecast.org/docs/icecast-latest/admin_interface/).

En tu salida MP3, artista y título pueden aparecer combinados en el título ICY. Los tags del archivo original no atraviesan automáticamente el recorrido de audio Windows → consola → USB: se deben obtener de la app reproductora y volver a publicar por un mecanismo de metadatos. Esta última conclusión es una inferencia técnica sobre tu recorrido de audio.

**Tu servidor es Icecast-KH.** Su código MP3 contempla etiquetas `artist`, `title` y `url`, y puede emitir la URL como `StreamUrl`. Es una posibilidad real para enviar un enlace de portada a reproductores compatibles; no transporta el archivo de imagen ni garantiza que AzuraCast lo incorpore a `song.art`. La vía de actualización MP3 examinada no trata `album` como una etiqueta equivalente. Hace falta validar el comportamiento de la compilación KH22 y sus permisos antes de implementar esta salida. [Implementación KH](https://github.com/karlheyes/icecast-kh/blob/master/src/format_mp3.c).

Para aprovecharlo necesitaríamos una imagen accesible por HTTPS, publicación sincronizada de URL/título y comprobación en cada reproductor. Una ruta local `C:\...` no es una URL que pueda consultar un oyente. Además, Liquidsoap o RadioCaster podrían sobrescribir las actualizaciones: debe haber un único escritor responsable por destino.

El manejador administrativo KH contempla además el parámetro `artwork`, pero lo asigna a una estadística: no es una carga del archivo de imagen ni prueba que el reproductor de AzuraCast lo use. Otro detalle importante: la rama de rechazo de actualización examinada puede responder `<return>1</return>` acompañada de un mensaje de rechazo. **El conector directo actual de MetaDATA comprueba ese código numérico y debe reforzarse antes de dar por confirmada una entrega a KH**: revisar el mensaje y, sobre todo, leer de vuelta el título/URL realmente publicados. No se aplicó ninguna actualización para comprobarlo en el servidor real. [Código administrativo KH](https://github.com/karlheyes/icecast-kh/blob/master/src/admin.c).

Ogg Vorbis sí define etiquetas separadas como ARTIST, TITLE, ALBUM, DATE, GENRE e ISRC. Eso describe el formato; no garantiza que RadioCaster las publique todas ni que cada servidor/reproductor las muestre. Cambiar a Ogg exclusivamente para obtener portadas no resuelve la integración. [Especificación Xiph](https://xiph.org/vorbis/doc/v-comment.html).

Otras capacidades útiles: consultar mounts y oyentes, mover oyentes entre fuentes compatibles, configurar respaldo al desconectarse una fuente, limitar conexiones y establecer relays. El respaldo por desconexión no equivale a detectar silencio acústico. [Administración](https://www.icecast.org/docs/icecast-latest/admin_interface/), [configuración](https://www.icecast.org/docs/icecast-2.4.1/config-file.html).

Para monitoreo conviene JSON/XML, no extraer texto de la página visual. `/status-json.xsl` expone datos que pueden variar según formato y estado. MetaDATA podría comparar título esperado y título remoto, detectar desconexiones y mostrar oyentes. Eso seguiría sin comprobar qué audio cruzó la consola. [Estadísticas](https://www.icecast.org/docs/icecast-latest/server_stats/).

## 5. AzuraCast: tres mecanismos distintos para las portadas

### A. Búsqueda automática para canciones en vivo

En Administración → Ajustes del sistema → Servicios → Album Art, la versión 0.20.2 incluye el interruptor para consultar servicios web en las canciones actuales y un campo de clave Last.fm. Los nombres traducidos pueden variar. Esta opción exige permisos globales; no basta necesariamente con administrar una estación. [Interfaz de esa versión](https://github.com/AzuraCast/AzuraCast/blob/0.20.2/frontend/components/Admin/Settings/ServicesTab.vue).

El proyecto tiene lectores de MusicBrainz y Last.fm; este último puede usar álbum cuando el objeto de canción lo tenga, o buscar por artista y título. Encontrar una imagen no garantiza acertar edición, recopilación o versión. [MusicBrainz](https://github.com/AzuraCast/AzuraCast/blob/main/backend/src/Media/AlbumArtHandler/MusicBrainzAlbumArtHandler.php), [Last.fm](https://github.com/AzuraCast/AzuraCast/blob/main/backend/src/Media/AlbumArtHandler/LastFmAlbumArtHandler.php).

### B. Biblioteca/AutoDJ y portadas de respaldo

AzuraCast puede trabajar con archivos de su biblioteca y sus carátulas, y resolver imágenes remotas o de respaldo del DJ/estación. La API de carga de portada exige un **media_id de un archivo de esa estación**; no es una carga genérica de imagen para cualquier canción en vivo. [Resolución de portada](https://github.com/AzuraCast/AzuraCast/blob/0.20.2/backend/src/Entity/ApiGenerator/SongApiGenerator.php), [carga de portada de biblioteca](https://github.com/AzuraCast/AzuraCast/blob/main/backend/src/Controller/Api/Stations/Art/PostArtAction.php).

Una biblioteca de respaldo permite seguir emitiendo desde AutoDJ cuando no esté el estudio. Se pueden subir archivos sin agregarlos a rotación; sincronizar una biblioteca no obliga a emitirla inmediatamente. No se presupone que subir un archivo haga coincidir automáticamente una canción externa con su portada. [Gestión de archivos](https://www.azuracast.com/docs/user-guide/media-management/).

### C. Carátula exacta de MetaDATA

Si queremos usar la imagen que leemos de cada archivo local, conservar el álbum exacto y forzar el logo durante anuncios, hace falta una integración adicional. Una propuesta es publicar JSON e imágenes en un servicio HTTPS y usarlos en un reproductor propio. Otra es desarrollar un plugin del servidor que vincule esos datos con la canción actual de AzuraCast. Su sistema de plugins permite extender comportamiento; la integración concreta todavía debe desarrollarse y probarse. [Plugins](https://www.azuracast.com/docs/developers/plugins/).

Esto ofrece control sobre el resultado, pero exige alojamiento/permisos y sincronización. No está implementado en MetaDATA. Activar la búsqueda remota no garantiza por sí solo que un mensaje de estación siempre produzca el logo: el reproductor propio puede usar explícitamente `is_music=false` para decidirlo.

## 6. Hallazgo importante: la API de actualización no acepta todos los campos

En 0.20.2 existe la ruta autenticada `/api/station/{station_id}/nowplaying/update`, aunque no aparece en el OpenAPI público descargado de tu instalación. Las rutas del código la vinculan al permiso de Broadcasting. Se verificó su definición en código; **no se llamó en tu estación**. [Rutas de 0.20.2](https://github.com/AzuraCast/AzuraCast/blob/0.20.2/backend/config/routes/api_station.php).

El controlador permite `title`, `artist`, `duration`, `song_id`, `media_id` y determinados parámetros técnicos. **No permite `album`, `year`, `genre`, `art` ni `url`** por esa vía. Enviar esos nombres no hará que se apliquen, aunque la respuesta general indique éxito. [Filtro explícito](https://github.com/AzuraCast/AzuraCast/blob/0.20.2/backend/src/Controller/Api/Stations/UpdateMetadataAction.php).

En 0.23.9 el filtro está en otra parte de la cadena, pero tampoco incluye álbum o imagen. Por tanto, no propongo una actualización de versión como solución automática a ese problema. [Lista permitida 0.23.9](https://github.com/AzuraCast/AzuraCast/blob/0.23.9/backend/src/Event/Radio/AnnotateNextSong.php), [aplicación del filtro](https://github.com/AzuraCast/AzuraCast/blob/0.23.9/backend/src/Radio/Backend/Liquidsoap/ConfigWriter.php).

Además, el feedback de una canción externa sin `media_id` construye el registro musical a partir de artista/título. La existencia del campo `album` en una respuesta JSON no prueba que se acepte al escribir por esta ruta. La posibilidad técnica de vincular `media_id` se debe reservar para pruebas con archivos propios de la estación; no se debe simular una referencia a otra canción para conseguir una imagen. [Feedback 0.20.2](https://github.com/AzuraCast/AzuraCast/blob/0.20.2/backend/src/Radio/Backend/Liquidsoap/Command/FeedbackCommand.php).

## 7. Matriz de datos y vías disponibles

| Información | Archivo normal para RadioCaster | Stream MP3/KH | AzuraCast / otra vía |
| --- | --- | --- | --- |
| Artista y título | Sí, normalmente combinados | Sí, título ICY; KH también maneja etiquetas de artista/título | Lectura Now Playing; escritura autenticada con límites |
| Álbum | Puede formar parte del texto; salida separada no verificada | No como campo estándar por la vía MP3 examinada | Biblioteca; servicio/plugin adicional para controlar álbum externo |
| Año, género musical, ISRC | No se verificó envío independiente | No asumir transporte por ICY | Algunos existen en biblioteca/API; recopilar y publicar por integración específica |
| Nombre, web, género y descripción de estación | Ajustes Station Info del encoder | Información de estación; distinta de la canción | Perfil de estación y datos públicos |
| Duración y progreso | No se verificó envío independiente | ICY no proporciona un progreso musical universal | AutoDJ tiene datos propios; para vivo requiere tratamiento adicional |
| Portada exacta local | No se verificó envío dinámico nativo | Posible enlace `StreamUrl` en KH; compatibilidad condicionada | Servicio/plugin propio o biblioteca vinculada correctamente |
| Portada encontrada en Internet | No es función documentada de la lectura TXT | No aparece automáticamente por el título | Búsqueda remota de AzuraCast |
| Logo durante anuncios | La app puede cambiar el título | Cambiar URL de imagen sería una integración adicional | Respaldo o reproductor que aplique una regla explícita |
| Fuente realmente audible en consola | No | No | No; requiere intervención del operador o información adicional del hardware |

La matriz sintetiza los manuales y código citados arriba; «no verificado» no significa que todas las versiones o extensiones lo impidan.

## 8. Otras funciones aprovechables

AzuraCast puede ofrecer Now Playing e historial a una web/app mediante HTTP y actualizaciones en tiempo real, manteniendo audio y datos como conexiones separadas. Se puede consultar también la URL de imagen actual; un reproductor debe actualizarla cuando cambie la canción, no asumir que una imagen estática se refrescará sola. [Now Playing](https://www.azuracast.com/docs/developers/now-playing-data/), [URL de imagen explicada por el mantenedor](https://github.com/AzuraCast/AzuraCast/discussions/5690).

Los mounts permiten distintas calidades/formats de una misma programación. Las conexiones DJ pasan normalmente por Liquidsoap para alternar con AutoDJ; pueden grabarse programas en vivo. Estas funciones no requieren cambiar la ruta física del estudio. [Mounts](https://www.azuracast.com/docs/user-guide/mount-points/), [DJs y grabación](https://www.azuracast.com/docs/user-guide/streamers-and-djs/).

También se pueden administrar archivos, listas, horarios, solicitudes, servicios y webhooks según los permisos de la cuenta. Los eventos/webhooks servirían para avisos de cambios o integraciones futuras; no se configuró ninguno ni se enviaron mensajes. [API y autenticación](https://www.azuracast.com/docs/developers/apis/), [listas programadas](https://www.azuracast.com/docs/user-guide/playlists/).

AzuraCast puede emitir a un servidor secundario mediante Remote Relay y sumar sus estadísticas cuando se puedan consultar. Es una alternativa a dos conexiones desde RadioCaster: debe comprobarse si el secundario admite la conexión y qué metadatos conserva. No presupone que «Xeno.fm» sea Zeno.fm ni que sus portadas se repliquen. [Relays](https://www.azuracast.com/docs/user-guide/remote-relays/).

## 9. Camino recomendado para ORO FM

1. **Primera prueba real:** MetaDATA → archivo UTF-8 → RadioCaster → entrada correcta de AzuraCast. Verificar artista/título y sustitución por mensaje durante un anuncio. Mantener el audio de consola actual.
2. **Portadas automáticas:** comprobar el ajuste global de búsqueda, poner canciones conocidas y revisar la imagen en la API/reproductor. Registrar coincidencias erróneas y tiempo de actualización.
3. **Datos completos locales:** ampliar Snapshot, JSON e historial con álbum, año, duración, ISRC y procedencia de imagen cuando la fuente los entregue. No significa que el stream los reciba; es una ampliación pendiente del proyecto.
4. **Confirmación remota:** agregar a MetaDATA lectura del Now Playing de la estación 2 y del estado Icecast, mostrando diferencias entre título esperado y recibido.
5. **Portada exacta y logo:** decidir entre reproductor propio con JSON/imágenes o plugin AzuraCast. Investigar `StreamUrl` como salida adicional para reproductores compatibles; no usarlo como sustituto de la integración con el panel.
6. **Después:** medir retardo por destino y evaluar relay/AutoDJ de respaldo. No activar una segunda ruta de escritura sobre el mismo mount sin definir qué proceso tiene autoridad.

## 10. Pruebas pendientes y datos necesarios

Se necesita confirmar en el panel la versión real y los permisos de administrador/estación; en Windows, versión exacta de RadioCaster y conexión usada (entrada DJ Liquidsoap o Icecast directo). Las consultas públicas no revelan esos datos ni si la búsqueda remota está activada. Las claves se introducirían localmente cuando toque conectar, no en el informe ni en el chat.

Las pruebas de aceptación deben cubrir: canción con portada conocida; canción sin portada; dos ediciones con mismo título; artista/título con acentos y guiones; anuncio con tags completos; mensaje de estación; pausa de ambas fuentes; cambio de prioridad; pérdida y recuperación de conexión; cierre del proceso; caché de imágenes; diferencias de retardo entre panel, reproductor y audio.

El botón de mensaje debe activarse antes del anuncio, y un fallo de conexión puede dejar datos anteriores en un destino. Obtener título remoto correcto tampoco demuestra que la consola esté pasando esa canción. Estas limitaciones deben conservarse en la interfaz y en los criterios de aceptación.

MetaDATA sigue con su implementación inicial. Este trabajo agrega investigación y evidencia; **no instala plugins, no cambia ajustes de la estación ni incorpora todavía los nuevos conectores**.
