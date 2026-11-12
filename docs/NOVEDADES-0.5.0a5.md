# MetaDATA 0.5.0a5: un solo formato de título

Se vuelve a un único selector **Formato del título combinado** en Ajustes → Now Playing. El formato elegido se aplica al texto de TXT, XML/CASTTITLE y JSON/text, así como al texto combinado de la aplicación. El valor predeterminado es **Artista - Canción**.

Se conservan las opciones predefinidas, las plantillas personalizadas y la vista previa. Los campos separados de artista, título y álbum mantienen su significado. Al elegir otro orden se mantiene el aviso de que un receptor que interpreta el texto por guiones puede intercambiar los campos. Cada reproductor decide cómo muestra los datos recibidos; un formato de texto no impone un diseño universal.

Al cargar una configuración de la versión con formatos separados se conserva el último **Texto para el emisor** como formato único y se guarda la configuración anterior en `config.split-title.backup.json`. Se elimina la opción separada del archivo activo. Las configuraciones de un solo formato conservan su selección existente.

Los campos `display_text` y XML/DISPLAYTITLE permanecen como alias de compatibilidad, con el mismo texto combinado. En pausas, anuncios y caducidad continúan vacíos. No se modifica el historial del servidor ni su reproductor.
