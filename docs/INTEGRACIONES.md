# Interfaces y límites verificados

Consulta documental: **9 de noviembre de 2026**. «Documentado» significa respaldado por el proveedor; no significa probado contra tu estación. **Actualización 0.4.0a3:** la aplicación genera salidas independientes del emisor. Se retiraron de la interfaz y del motor la publicación directa Icecast/AzuraCast y el monitor remoto. Las referencias a esos conectores en la tabla siguiente documentan investigación e implementaciones heredadas, no funciones activas. Consulta [la guía actual de conexiones](CONEXIONES.md).

La investigación ampliada y las consultas públicas de ORO FM están en [el informe RadioCaster/Icecast/AzuraCast](../outputs/Investigacion-RadioCaster-Icecast-AzuraCast.md). La API de `orofm.live` declara 0.20.2 y su servidor de audio se identifica como Icecast 2.4.0-kh22. Se confirmó en el código de AzuraCast 0.20.2 que la actualización en vivo admite artista/título, pero filtra álbum y URL/imagen de portada; la búsqueda remota de carátulas es un mecanismo separado. No se modificó la estación.

| Integración | Documentado / implementado | Límite pendiente |
| --- | --- | --- |
| RadioBOSS local | API HTTP: `action=playbackinfo`, XML CurrentTrack/TRACK y Playback; lectura `readtag` con `artwork=1`, TypeIdentifier e imagen base64. Implementado. | Confirmar versión, acceso API, rutas y tipos de tus archivos. No cubre necesariamente cartucheras, overlays, micrófono ni mezcla de varios reproductores internos. |
| Spotify local en Windows | Microsoft documenta sesiones de otras apps, identificador de app, estado y propiedades multimedia; implementado mediante PyWinRT. | La participación de Spotify en SMTC, sus campos y miniaturas deben comprobarse en la PC. No garantiza clasificar anuncios. Solo estado local reportado; no es medición de audio. |
| Spotify Web API | Endpoint OAuth de reproducción actual con `is_playing`, objeto musical e imágenes del álbum. Investigado, **no implementado**. | Es del usuario/cuenta y puede reflejar Spotify Connect en otro dispositivo; no prueba reproducción en esta PC. Requiere autorización y está sujeto a políticas/acceso de Spotify. |
| RadioCaster | Lectura de nombre desde archivo o URL documentada. Implementadas salidas UTF-8 TXT/XML y servicio local de lectura opcional. | Configurar manualmente la lectura y comprobar codificación/cadencia. Sin API de control RadioCaster en esta versión. |
| Icecast | Actualización textual `/admin/metadata`, `mount`, `mode=updinfo`, `song`; conector opcional implementado. | Depende de permiso, servidor activo, formato y respuesta. URL de carátula opcional para KH después de subirla a un alojamiento; lectura de confirmación configurable. No envía imagen binaria dentro del stream. |
| AzuraCast | Ingesta en vivo por software de emisión. Ruta propuesta: archivo → RadioCaster → conexión DJ existente. | Liquidsoap puede intermediar; no confundir puerto DJ y mount de escucha/admin Icecast. Verificar título en panel/reproductor. Conector REST opcional implementado solo para artista/título; monitor de lectura independiente. |
| AzuraCast carátulas | El proyecto documenta resolución de carátulas y portada predeterminada del DJ/estación. | No se implementa carga de portada arbitraria a la API de AzuraCast. Se implementa reproductor propio y alojamiento WebDAV opcional. Una portada que aparezca en el reproductor no prueba que llegó desde esta app. |
| Zeno.fm (destino secundario confirmado por el usuario) | Documenta emisión con encoder compatible con Icecast y una API de suscripción de metadatos para lectura. | La API de suscripción **no es una API de escritura**. Validar títulos vía encoder, credenciales y mount de su panel. No se afirma soporte para carátula dinámica. |

## Fuentes primarias

- [DJSoft: API RadioBOSS](https://manual.djsoft.net/radioboss/en/remote_controlapi.htm) y [activación/configuración](https://manual.djsoft.net/radioboss/en/remote_control_api.htm). El código utiliza únicamente acciones de lectura y no envía comandos de reproducción.
- [DJSoft: fuentes de metadatos RadioCaster](https://manual.djsoft.net/radiocaster/en/metadata.html). Se utiliza lectura de archivo; también documenta lectura de XML, URL y texto fijo. No se deduce de esta página un mecanismo de carátulas.
- [Microsoft: GlobalSystemMediaTransportControlsSession](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession) y [ejemplo de consulta de sesiones](https://devblogs.microsoft.com/oldnewthing/20231108-00/?p=108980). La API observa lo que las apps publican en Windows; no inspecciona la consola.
- [PyWinRT: instalación modular](https://pywinrt.readthedocs.io/en/latest/installing/) y [hilos y apartments](https://pywinrt.readthedocs.io/en/latest/threads/). El lector WinRT se ejecuta en el trabajador, fuera del hilo de interfaz.
- [Spotify: Get Currently Playing Track y notas de política](https://developer.spotify.com/documentation/web-api/reference/get-the-users-currently-playing-track). La plataforma indica una restricción de radiodifusión no interactiva. Leer metadatos locales no concede derechos sobre el audio.
- [Icecast: interfaz administrativa](https://www.icecast.org/docs/icecast-latest/admin_interface/). El endpoint documentado actualiza texto; aquí no se presupone un campo estándar de carátula transportada como imagen. Extensiones particulares o el uso de StreamUrl no implican compatibilidad universal con reproductores.
- [AzuraCast: software de emisión](https://www.azuracast.com/docs/user-guide/streaming-software/), [APIs](https://www.azuracast.com/docs/developers/apis/), [explicación de resolución de imágenes por su mantenedor](https://github.com/AzuraCast/AzuraCast/discussions/6171), [portada del DJ en vivo](https://features.azuracast.com/suggestions/334270/upload-custom-artwork-for-live-broadcast). No se ha verificado una API general de carga de portada arbitraria por canción en vivo en la instalación del usuario; el proyecto no simula que la tiene.
- [Zeno: emisión con encoder](https://help.zeno.fm/en/article/i-already-have-a-radio-station-how-can-zeno-tools-help-me-l5x104/) y [Metadata API](https://help.zeno.fm/en/article/what-is-the-metadata-api-wh2c9s/). El usuario confirmó que Zeno.fm es el destino secundario; estas referencias corresponden al proveedor correcto.

## Lo que se puede inferir y lo que no

Cuando RadioBOSS reporta play y Spotify no, se selecciona RadioBOSS. Si ambas apps reportan reproducción, la prioridad o selección manual resuelve **qué metadatos** usar. Ninguno de esos datos informa sobre faders, mute, retorno USB, FXSound ni el contenido real de la mezcla física. No se afirma reconocimiento infalible de la fuente al aire.

Que artista y título estén completos no demuestra que sea música. Para RadioBOSS se añade una lista de carpetas permitidas, exclusiones y tipos. Para Spotify la clasificación depende de lo reportado por Windows y reglas locales. No se llama a bases externas de carátulas ni se hace scraping de ventanas. Si se necesita garantía operativa de no mostrar anuncios, utiliza el control de mensaje de estación antes de cada bloque y conserva una biblioteca clasificada.

La sincronía exacta entre texto, audio codificado y reproducción remota no se ha medido. El monitor 0.2 compara las últimas consultas remotas; aún se debe medir el retardo frente al audio para decidir si hace falta una cola de publicación por destino.

## Estado tras la adaptación 0.2

Las funciones implementadas y los límites pendientes están en [Novedades 0.2](NOVEDADES-0.2.md). La búsqueda externa de portadas, AutoDJ, grabaciones y relays siguen siendo ajustes del panel de AzuraCast. No se instalaron plugins ni se modificó la estación durante el desarrollo.

## Cambios de operación 0.3

La interfaz y las claves se describen en [Novedades 0.3](NOVEDADES-0.3.md). En pausas ya no se publica el mensaje de estación como título. El logo se usa como portada de respaldo únicamente para canciones válidas sin imagen, y como identidad visual del reproductor. El historial remoto pertenece a cada servicio; un vaciado no garantiza eliminar entradas ni retirar inmediatamente el último título de todos los clientes.
