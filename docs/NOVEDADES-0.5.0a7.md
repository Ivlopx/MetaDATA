# MetaDATA 0.5.0a7: inicio y bandeja

Se incorporan las preferencias en **Ajustes → Inicio y bandeja**:

- **Iniciar MetaDATA al iniciar sesión en Windows:** arranque automático para el usuario actual. Se aplica al guardar; desmarcar y guardar elimina la entrada propia de ese perfil.
- **Arrancar oculta en la bandeja del sistema:** funciona al abrir la app, tanto con inicio automático como manual. No oculta inmediatamente la ventana en la que estás configurando.
- **Ocultar en la bandeja al minimizar:** evita mantener la ventana en la barra de tareas cuando hay bandeja disponible.
- **La X oculta la ventana y mantiene la app funcionando:** permite conservar el comportamiento anterior o elegir que la X cierre realmente el programa.

Restaurar desde el menú del icono abre la ventana. **Salir** siempre termina la app y su procesamiento, intentando vaciar los metadatos musicales por las salidas activas. Sin bandeja disponible, el arranque oculto minimiza la ventana para que sea recuperable, y la X cierra. Las preferencias antiguas conservan el comportamiento anterior: sin inicio automático, ventana visible y cierre a bandeja cuando existe.

## Cómo probarlo

1. Actualiza el proyecto y vuelve a ejecutar instalar.bat. Si usas un EXE, vuelve a construirlo con la versión actual: un EXE ya generado no se actualiza con git pull.
2. Abre Ajustes → Inicio y bandeja, elige las opciones y guarda.
3. Cierra mediante Salir y vuelve a abrir para probar el arranque oculto. Restaura desde el icono de MetaDATA en la bandeja.
4. Prueba minimizar y cerrar con la X según tus preferencias.
5. Para comprobar el inicio con Windows, cierra y vuelve a iniciar tu sesión. Esta comprobación debe hacerse en tu PC Windows.

No hace falta configurar variables de entorno ni crear accesos directos manualmente. Si ya habías creado un acceso directo manual en la carpeta Inicio, retíralo al usar esta opción para evitar lanzar dos copias.

## Implementación

Se utiliza una entrada propia por carpeta de datos en `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`. No se cambian otras aplicaciones ni se requiere elevación normal. Las rutas con espacios se pasan con el escape de línea de comandos de Windows. El comando incluye el perfil de datos y no contiene claves. En una instalación Python utiliza pythonw.exe y el módulo instalado por instalar.bat; en un paquete generado con PyInstaller apunta al EXE actual, sin pedir Python externo para arrancar la interfaz.

Si mueves la carpeta del programa, abre desde la nueva ubicación y vuelve a guardar el ajuste para actualizar la ruta. Windows puede retrasar el arranque o deshabilitarlo desde sus propias opciones de Aplicaciones de inicio; la app no anula esa preferencia del sistema.

El guardado restaura la entrada anterior si falla el almacenamiento de claves o configuración. La demostración nunca modifica el inicio de Windows. Las rutas que superen el límite de Run se rechazan antes de escribir. Se pueden usar `--hidden` para iniciar oculta y `--show` para mostrar la ventana aunque esté configurado el arranque oculto; son opciones de inicio de una nueva instancia, no reemplazan Restaurar si ya está ejecutándose.

Referencia: [Run y RunOnce en la documentación de Microsoft](https://learn.microsoft.com/en-us/windows/win32/setupapi/run-and-runonce-registry-keys).

Las pruebas locales cubren los comandos para Python/EXE, el registro simulado del usuario actual, activación y desactivación, reversión ante errores, guardado y cancelación, inicio oculto, restauración, minimizado y cierre. El inicio real al iniciar sesión y el comportamiento de la bandeja deben confirmarse en Windows.
