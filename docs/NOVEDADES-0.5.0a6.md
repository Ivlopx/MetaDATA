# MetaDATA 0.5.0a6: enfoque en metadatos

Se retiran las funciones que pedían un enlace de audio y comprobaban la emisión:

- Desaparece Monitoreo de la ventana principal y de Ajustes, junto con estadísticas e incidentes.
- Desaparece la sección Carátulas que configuraba el audio, el reproductor local y el alojamiento WebDAV.
- Se elimina el botón Abrir reproductor y los ajustes de su servidor local. Ya no se genera player.html ni se exporta stream_url.
- Las configuraciones anteriores no vuelven a iniciar monitoreo, consultas de oyentes, servidor local ni WebDAV. Al guardar ajustes se desactivan sus opciones antiguas.

Inicio también agrupa título, artista y álbum con menor separación. Sin una canción válida, el lugar del título muestra la descripción de la estación; artista y álbum quedan vacíos y ocultos. Si la descripción está vacía indica Sin reproducción. Se eliminan de Ajustes los antiguos mensajes de pausa y anuncios. La descripción es solo visual y nunca se publica como título musical.

Las portadas de las canciones se conservan: siguen obteniéndose de las fuentes, mostrándose en Inicio, guardándose en covers con sus límites y enviándose junto con el JSON al receptor desde Publicación. También se mantienen el logo de respaldo para canciones reales sin imagen, la exclusión de anuncios, las fuentes y prioridades, el historial, Now Playing y los encoders.

La aplicación vuelve a cuatro pantallas: Inicio, Historial, Conexiones y Ajustes. Ctrl+1 a Ctrl+4 cambia entre ellas. No se borra el historial de canciones ni se eliminan automáticamente archivos o claves de funciones retiradas.

La verificación incluye un perfil antiguo con todas las opciones retiradas activadas: el motor no abre consultas de audio/estadísticas ni el servidor local, no crea una base de monitoreo y sigue generando los metadatos. La instalación y el despliegue permanecen para el final.
