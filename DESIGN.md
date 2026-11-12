# MetaDATA: criterios de interfaz

Aplicación de escritorio para operar metadatos y comprobar una emisión. La prioridad es reconocer qué está seleccionado, qué datos se publican y qué requiere atención. Los controles habituales deben poder usarse sin leer documentación técnica.

## Referencia y adaptación

Se revisaron los sistemas [Minimal](https://github.com/nexu-io/open-design/blob/614795896e09a2c1682b24cc1406529baf531bd7/design-systems/minimal/DESIGN.md) y [Professional](https://github.com/nexu-io/open-design/blob/614795896e09a2c1682b24cc1406529baf531bd7/design-systems/professional/DESIGN.md) de OpenDesign: jerarquía, espaciado regular, acciones explícitas y ornamentación contenida. Se adaptan a PySide6 y al tema de Windows, conservando controles nativos. No se copiaron CSS, componentes web, tipografías ni paletas. Esta revisión usa esos recursos documentados; no ejecuta OpenDesign Studio ni un servicio de diseño externo.

## Jerarquía

- Inicio: canción, artista, álbum, fuente y controles de uso diario. La carátula acompaña la información.
- Historial: registro musical y exportación.
- Conexiones: estado de las fuentes separado del estado de las salidas. Cada acceso de configuración lleva a la sección correspondiente.
- Ajustes: un formulario integrado y persistente, con navegación propia. Evitar lanzar una segunda ventana de configuración o una página de botones que repita ese menú.

## Lenguaje visual

La paleta y la tipografía proceden del sistema operativo. El acento de Windows indica selección y foco. El color semántico se reserva para estados con texto: correcto, advertencia, error y sin comprobar. Los iconos de reproductores identifican las fuentes; no indican por sí solos disponibilidad o reproducción.

Usar márgenes de 16–20 unidades lógicas en paneles, separaciones de 8–16 y una escala de 4/8/12/16/24 para componentes nuevos. Los títulos de sección usan la fuente del sistema con tres puntos adicionales; la canción tiene cinco puntos adicionales. El énfasis se concentra en títulos y datos principales. Los botones conservan su aspecto nativo y un ancho proporcionado a la acción; no expandirlos a toda la pantalla por defecto.

## Una ubicación por tarea

Las rutas, el selector único de formato del título y los botones de copiar/abrir archivos pertenecen a Now Playing. El texto combinado mantiene un solo formato en todas las salidas. Por compatibilidad se usa Artista - Canción por defecto y se avisa si se selecciona otro formato que pueda afectar a su interpretación. No repetir esta barra en Inicio o Historial. La configuración vive en Ajustes; los accesos desde otras pantallas son atajos al mismo formulario y mantienen sus cambios pendientes.

Las instrucciones específicas de emisores se agrupan bajo una ayuda desplegable. El eslogan opcional y las plantillas personalizadas también se muestran cuando se solicitan.

## Comportamiento

Guardar aplica la configuración al motor y actualiza los estados. Descartar restaura la configuración aplicada y elimina las claves pendientes, sin cambiar el almacén de credenciales. Cambiar de pestaña no descarta el formulario. Enter en un campo no guarda automáticamente. Las comprobaciones en curso impiden destruir su formulario; ocultar en la bandeja sigue permitido. Inicio y bandeja reúne el inicio con Windows, el arranque oculto, el minimizado y la elección de ocultar o cerrar con X. Salir siempre termina la app; si no hay bandeja se mantiene una ventana recuperable. El inicio automático está desactivado inicialmente y solo se registra al guardar esa preferencia.

Atajos de Windows: Ctrl+1 a Ctrl+4 cambian de pantalla; Ctrl+, abre Ajustes. Ctrl+S guarda cuando el foco está dentro de Ajustes. Las tablas y los campos conservan la navegación nativa por teclado. Los mensajes de estado y errores se muestran como texto plano.

## Información progresiva

Inicio agrupa título, artista y álbum con un espaciado compacto. Sin canción válida usa la descripción en el lugar del título y oculta artista y álbum; no usa mensajes de pausa o anuncios y no exporta la descripción como canción. También presenta un motivo breve; la limitación de la selección respecto de la consola permanece en la ayuda del motivo y en los detalles. Los mensajes de diagnóstico están disponibles bajo Mostrar detalles. Las funciones desactivadas no se muestran como errores. Un archivo generado no se presenta como confirmación de emisión.

## Validación

Revisar Inicio, Conexiones y Ajustes con los mismos datos de demostración antes y después. Comprobar el tamaño habitual de 960×680 y el mínimo de 760×560. Verificar que Guardar/Descartar, navegación, credenciales y rutas siguen funcionando y que hay un único control de archivos en la ventana principal. La comprobación nativa de apariencia clara/oscura y escala de Windows se realiza en Windows; las capturas locales de desarrollo no sustituyen esa validación.

## Alcance

No incluir monitoreo de audio, estadísticas de oyentes, reproductor local ni campos de enlace de audio. Las carátulas son metadatos de las canciones y siguen apareciendo en Inicio, la caché y las salidas compatibles. La publicación del JSON y la portada al receptor se configura en Publicación.
