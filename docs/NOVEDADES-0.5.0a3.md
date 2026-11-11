# MetaDATA 0.5.0a3: interfaz simplificada

Se aplicaron criterios de los sistemas Minimal y Professional de OpenDesign al escritorio nativo, respetando el tema de Windows. Los criterios se mantienen en [DESIGN.md](../DESIGN.md).

- Ajustes contiene el formulario directamente; desaparece la página intermedia de botones y las ventanas adicionales al configurar desde Conexiones.
- Un único formulario mantiene sus cambios al navegar. Guardar aplica los cambios; Descartar los restaura sin guardar claves pendientes.
- Las rutas y botones de archivos están en Ajustes → Now Playing. Se conserva copiar ruta, abrir carpeta y elegir XML/TXT/JSON.
- Inicio agrupa la reproducción y sus controles; el historial reciente muestra un mensaje cuando todavía no hay canciones.
- Conexiones separa Fuentes de reproducción y Salidas de metadatos, con indicadores y texto.
- La ayuda de integración y los campos avanzados de WebDAV se despliegan cuando se necesitan.
- Se mantienen los controles nativos, con espaciado consistente y botones de ancho contenido. La vista es utilizable al reducir la ventana.
- Ctrl+1 a Ctrl+5 cambian de pantalla y Ctrl+, abre Ajustes. Ctrl+S guarda dentro de Ajustes. Enter en un campo no guarda accidentalmente.

Las funciones de fuentes, formatos, encoders, publicaciones y monitoreo se conservan. Instalador y despliegue permanecen al final.

Se verificaron el guardado, descarte, navegación, protección de credenciales pendientes y control único de rutas, además de la suite de integraciones. Se revisaron capturas de demostración a tamaño normal y compacto. El aspecto nativo del tema y la escala deben comprobarse en Windows.
