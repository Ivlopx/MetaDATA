# MetaDATA 0.5.0a2

El formato visual y el texto emitido se separaron en [0.5.0a4](NOVEDADES-0.5.0a4.md) para evitar invertir artista y canción en el servidor.

- **Monitoreo:** recepción y decodificación real del audio, medición de nivel y detección de silencio en muestras configurables. Trabaja en paralelo al procesamiento de metadatos.
- **Incidentes:** apertura y cierre tras resultados consecutivos, historial persistente, conservación configurable y exportación de los 200 incidentes visibles.
- **Estadísticas:** lectura opcional de JSON genérico, Icecast o AzuraCast. Últimas muestras de oyentes simultáneos, pico y promedio de muestras en 24 horas; errores como desconocidos y medidas separadas por endpoint/montaje.
- **Formato de títulos:** lista desplegable con Canción - Artista, Artista - Canción, Solo canción, Canción - Artista (Álbum) y Personalizado, con vista previa. RadioCaster puede seguir usando `{TRACK[CASTTITLE]}`; cambia el texto desde MetaDATA.

Los campos estructurados conservan su significado. Cambiar el texto combinado no cambia artista, título ni álbum por separado, ni obliga a otros reproductores a adoptar un orden visual. Durante anuncios y pausas el texto musical sigue vacío.

Guía: [monitoreo, estadísticas y compatibilidad en Windows](MONITOREO.md).

La validación local incluye HTTP con audio normal y silencio decodificados mediante FFmpeg, fallos de conexión, recuperación de incidentes, límites de conservación, separación de estadísticas por servidor y guardado de formatos. La comprobación nativa de cada reproductor debe hacerse en Windows. El instalador y el despliegue permanecen para el final, según lo acordado.
