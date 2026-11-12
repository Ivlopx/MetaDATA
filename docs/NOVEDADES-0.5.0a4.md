# MetaDATA 0.5.0a4: artista y título al emitir

Se corrige una incompatibilidad: cambiar el texto combinado a Canción - Artista también cambiaba lo que el emisor publicaba como título ICY. Un servidor que interpreta ese texto como Artista - Canción puede intercambiar los campos, aunque ARTIST y TITLE del XML local sean correctos. Leer únicamente CASTTITLE no transporta al servidor los otros atributos del XML.

## Dos formatos independientes

En Ajustes → Now Playing:

- **Presentación en MetaDATA:** conserva tu formato visual, incluidos los personalizados. Se exporta como `display_text` en JSON y `DISPLAYTITLE` en XML; también se mantiene el texto de presentación en el modelo de la aplicación.
- **Texto para el emisor:** controla TXT, `CASTTITLE` y `text` del JSON. El valor predeterminado es **Artista - Canción**. Elegir otro formato muestra un aviso de compatibilidad.

RadioCaster puede mantener `{TRACK[CASTTITLE]}`. Para AzuraCast y receptores que interpretan un título combinado, conserva Artista - Canción en Texto para el emisor. El reproductor remoto decide el orden visual de los campos; transmitirlos al revés no es una forma segura de cambiar su diseño.

Las configuraciones anteriores adquieren el formato compatible de emisión al actualizar, sin perder su plantilla visual. No hace falta borrar la configuración. Los campos separados ARTIST/TITLE/ALBUM siguen correspondiendo a la canción real. En pausas, anuncios y caducidad se vacían tanto la salida como la presentación. El receptor autohospedado admite el campo de presentación adicional; los receptores antiguos pueden ignorarlo y seguir usando los campos musicales.

La corrección afecta a nuevas actualizaciones de metadatos. No modifica el historial previo del servidor ni el reproductor remoto, y no conecta directamente MetaDATA a un proveedor.

## Validación

Las pruebas reproducen un consumidor que separa por el primer guion: al cambiar la presentación, TXT y CASTTITLE siguen produciendo artista y canción correctos. También se comprueban la carga de ajustes anteriores, las plantillas personalizadas, el aviso de compatibilidad y el vaciado por pausa/caducidad. La comprobación final del servidor se realiza después de actualizar la app emisora.

Referencia: el [modelo musical de AzuraCast 0.20.2](https://github.com/AzuraCast/AzuraCast/blob/0.20.2/backend/src/Entity/Traits/HasSongFields.php) construye su texto combinado como artista, separador y título. Esto es distinto del orden en que un reproductor los presenta.
