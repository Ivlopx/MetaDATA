# Adaptación 0.2 a la investigación de ORO FM

## Disponible en la aplicación

- Datos ampliados de canciones: álbum, artista del álbum, año, género, ISRC, duración, posición y número de pista cuando estén disponibles. RadioBOSS obtiene sus tags y Spotify las propiedades multimedia de Windows. El año e ISRC no se inventan para Spotify.
- Historial con álbum y año en pantalla; la base conserva además género, duración, ISRC y procedencia de carátula. Se migran las tablas existentes sin perder filas.
- TXT compatible con RadioCaster y XML/JSON completos. Solo se exporta la selección musical aprobada o el mensaje de estación. Las rutas de archivos locales no se publican.
- Reproductor y servicio local opcionales: portada exacta, álbum, logo durante anuncios y mensaje de respaldo si caducan los datos. No reproduce audio automáticamente; el usuario debe pulsar Play.
- Monitor de lectura para AzuraCast e Icecast. Compara el título remoto con el seleccionado, muestra álbum, URL de imagen y hora de consulta. Los valores remotos no alimentan la selección, para evitar ciclos.
- Corrección de Icecast-KH: no se acepta un `<return>1</return>` que venga con un mensaje de rechazo. La lectura de confirmación opcional comprueba mount, título y URL de imagen.
- Escritura AzuraCast opcional limitada a artista y título, sin campos filtrados o parámetros técnicos como `media_id`/`liq_*`.
- Alojamiento WebDAV HTTPS opcional: sube imágenes antes que JSON, usa nombres por contenido y transmite credenciales solo al destino configurado, sin redirecciones. El JSON es el último archivo que se actualiza. El reproductor descarta música desactualizada si falla la subida.
- Opción StreamUrl para Icecast-KH: envía la URL pública de la portada subida y la vacía si no puede publicar la nueva. Su interpretación depende del reproductor.
- Guía dentro de la interfaz para búsqueda remota de carátulas, AutoDJ, grabaciones, mounts y relay secundario.

Los servicios nuevos comienzan desactivados. La demo no consulta ni publica a servidores aunque esos ajustes estén activados; permite la vista local si se habilita.

## Datos conservados al actualizar

La configuración antigua se guarda como `config.v1.backup.json` antes de actualizar su esquema a versión 2. No se reemplazan los datos personales de tu estación por los de ORO FM. El nombre/eslogan/mensajes siguen siendo los configurados por el usuario. Las direcciones e ID públicos de ORO FM están precargados únicamente para los nuevos ajustes de conexión.

## Límites que siguen vigentes

La integración WebDAV publica un reproductor propio y no instala un plugin ni fuerza la portada del panel de AzuraCast. Para eso haría falta desarrollo/instalación adicional en el servidor, o usar su búsqueda remota/biblioteca. No se activan ni cambian AutoDJ, grabaciones o relays automáticamente.

No se ha probado el lector nativo Windows ni se ha generado un EXE Windows en macOS. Tampoco se publicaron cambios en la estación real. Las claves se introducen localmente en variables de entorno cuando se configure la conexión.
