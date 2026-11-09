# MetaDATA 0.3

La pantalla principal se centra en la canción, su fuente y el control de pausa. Inicio, Historial, Conexiones y Ajustes separan tareas; los diagnósticos se despliegan solo cuando se necesitan. Los controles utilizan la apariencia de escritorio, sin una paleta fija. El tema predeterminado sigue Windows y admite selección clara/oscura.

Las claves se introducen, muestran, borran y prueban desde formularios. Windows Credential Manager conserva los secretos por usuario y perfil; no hay archivo de contraseñas. Cancelar no guarda secretos. Un error al guardar restaura las claves previas cuando el almacén lo permite y avisa si no puede compensar. Las pruebas de conexión son de lectura, sin publicación ni cambios de reproducción.

Icecast ya se configura mediante formularios, sin escribir JSON. La consulta de estadísticas comprueba el mount público, no la contraseña. La prueba autenticada de AzuraCast comprueba lectura de la estación, no autorización de escritura. RadioCaster sigue recibiendo un archivo; comprobar su existencia no confirma que el encoder esté leyéndolo.

La configuración migra de versiones 1/2 a 3 con respaldo, conserva prioridades, carpetas, salidas e historial y mantiene compatibilidad con claves de entorno antiguas hasta gestionar cada conexión desde el formulario. Las claves se separan por dirección/usuario y carpeta de datos. Tras cambiar esos datos, usar otro usuario de Windows o trasladar el perfil, vuelve a introducirlas.

El historial compacto conserva sus seis columnas y permite exportar todas las filas a CSV. Inicio muestra las últimas tres canciones. No se incorporan anuncios ni mensajes visuales al historial.

## Vaciado durante pausas

Por indicación del usuario se retira el antiguo mensaje de estación de las salidas musicales. Durante anuncios, pausas, errores y ausencia de canciones válidas se exportan artista, título, álbum y portada de canción vacíos. TXT contiene solo un salto de línea; XML no pone el nombre de la estación en TITLE; Icecast envía `song=` y retira la URL de imagen cuando esa salida está habilitada; AzuraCast recibe artista y título vacíos.

El JSON pasa al esquema 3: `text` representa únicamente la canción y es vacío sin música, `display_message` contiene un mensaje exclusivamente visual y `logo_file` identifica la imagen de la estación. `is_music` es falso en pausas. Un consumidor propio debe respetarlo en vez de tratar el mensaje o el logo como una pista.

Para una canción válida sin imagen se usa el logo configurado como respaldo y se mantienen los metadatos reales. La portada exacta/logo en AzuraCast sigue dependiendo de sus propios ajustes: su API de títulos no acepta cargar la imagen de MetaDATA.

La documentación de [Icecast](https://icecast.org/docs/icecast-trunk/admin_interface/) describe la actualización de metadatos. El [código de Icecast-KH](https://github.com/karlheyes/icecast-kh/blob/master/src/admin.c) aplica el parámetro song al título y permite retirar el artista; no aporta una opción de exclusión universal de historiales. El [manual de RadioCaster](https://manual.djsoft.net/radiocaster/en/metadata.html) documenta lectura desde archivo, pero no garantiza cómo trata el archivo vacío.

Es necesario verificar el vaciado en el estudio: otro escritor o una caché pueden mantener el título anterior. AzuraCast puede aplicar su información de respaldo o conservar historial; la app no borra su base de datos ni garantiza cómo lo presentan todos los servicios externos. No se enviaron pruebas a la estación real.

Se revisó también el [generador Now Playing de AzuraCast 0.20.2](https://github.com/AzuraCast/AzuraCast/blob/0.20.2/backend/src/Entity/ApiGenerator/NowPlayingApiGenerator.php): cuando no hay backend habilitado y el texto de canción está vacío, utiliza su respuesta de respaldo antes de registrar esa canción. Con backend habilitado sigue la información e historial de ese backend. Por tanto, el título vacío no implica por sí solo una presentación idéntica en todas las instalaciones, y puede aparecer la respuesta offline del panel aunque haya audio. No se cambia la configuración de la estación para ocultar esta diferencia.

## XML para RadioCaster

El XML añade CASTTITLE con el texto combinado de una canción y vacío en pausas. La configuración recomendada es Read from XML file, nowplaying.xml, Title Format `{TRACK[CASTTITLE]}`. Evita separadores fijos durante un vaciado, conserva atributos estructurados y mantiene el TXT como alternativa. La interfaz muestra ruta y plantilla. No se agrega un lector JSON inexistente a RadioCaster ni se presupone que Read from URL procese XML.
