# MetaDATA · versión 0.3.0

Aplicación de escritorio en español para Windows 11, Python 3.11 y PySide6. Administra metadatos; el audio continúa por Windows → FXSound → consola → USB → RadioCaster.

La interfaz utiliza controles de escritorio, colores del sistema y cuatro pantallas: **Inicio, Historial, Conexiones y Ajustes**. El tema sigue Windows por defecto y permite elegir claro u oscuro. Funciona en segundo plano con bandeja, ocultar y restaurar.

## Instalar y actualizar en Windows

Instala [Python 3.11 de 64 bits](https://www.python.org/downloads/windows/) y abre la carpeta del proyecto, que puede estar dentro de Documentos. Ejecuta **instalar.bat**; después **demo.bat** para probar con datos ficticios o **iniciar.bat** para las fuentes reales.

Para actualizar una copia clonada, primero cierra la app desde **Salir**, actualiza el repositorio y reinstala:

```powershell
git pull
.\instalar.bat
.\iniciar.bat
```

La configuración y el historial se conservan. Las configuraciones v1/v2 migran al esquema 3 con una copia `config.v1.backup.json` o `config.v2.backup.json`. No reemplaces tu configuración con el ejemplo si ya la personalizaste.

Instalación manual, dentro de la carpeta del proyecto:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m radio_metadata --demo
```

La demo usa historial y salida separados, permite simular canciones, anuncios y conflictos, y no consulta ni publica a servidores. No conectes su archivo a RadioCaster al aire. Para desarrollar, instala con `pip install -e .`.

## Configurar la estación

1. **Ajustes → Estación**: nombre, eslogan, web, descripción, logo y apariencia. Los mensajes sin música son solo visuales en MetaDATA y su reproductor.
2. **Conexiones → RadioBOSS → Configurar**: activa su API HTTP en RadioBOSS, indica dirección/usuario y escribe la contraseña en la app. Pulsa **Probar conexión** y **Guardar**. Usa localhost para esta instalación.
3. **Ajustes → Música**: agrega las carpetas de canciones. Excluye carpetas, términos y tipos de anuncios, promos y jingles. Sin carpetas aprobadas, RadioBOSS no publica canciones. No se deducen artista y título del nombre del archivo.
4. **Conexiones → Spotify**: consulta sus sesiones multimedia de Windows sin clave API ni OAuth. Empieza en observación; permite sus canciones en selección e historial cuando hayas comprobado el comportamiento. Windows no garantiza clasificar todos los anuncios. La app no concede derechos de retransmisión; consulta las condiciones de Spotify.
5. **Conexiones → RadioCaster** muestra el archivo que debes seleccionar en RadioCaster → Settings → Metadata → **Read from XML file**. En **Title Format** escribe `{TRACK[CASTTITLE]}`. Normalmente es:

   ```text
   %LOCALAPPDATA%\RadioMetadataManager\output\nowplaying.xml
   ```

   El TXT continúa disponible para **Read from file** con primera línea y UTF-8, si prefieres mantener esa entrada.
6. RadioCaster conserva sus encoders hacia **AzuraCast y Zeno.fm**. Sus claves de transmisión siguen en RadioCaster. No necesitas copiarlas a MetaDATA si usas esta ruta.

En Inicio selecciona Automático, Solo RadioBOSS o Solo Spotify. Si ambas reproducen, se aplica la prioridad. Una fuente elegida manualmente no cambia a la otra cuando se pausa. **Pausar metadatos** vacía los datos publicados y suspende las consultas de fuentes; **Reanudar automático** retoma la selección.

Cerrar con X oculta cuando existe bandeja. **Salir** termina el proceso y publica el vaciado de datos musicales por las salidas activas. Sin bandeja, Ocultar minimiza y X sale. El autoarranque no está implementado; puedes añadir un acceso directo a `iniciar.bat` en la carpeta de inicio de Windows después de validar la instalación.

## Pausas y carátulas

**Durante anuncios, pausas, errores o ausencia de una canción válida, artista, título, álbum y portada de canción quedan vacíos.** El archivo TXT contiene una línea vacía y el XML no convierte el mensaje de estación en título. La publicación Icecast envía el título vacío; la API AzuraCast envía artista y título vacíos. No se envían nombre ni eslogan como una canción ficticia.

El JSON distingue los campos musicales de `station`, `slogan`, `logo_file` y `display_message`, que son identidad y presentación del reproductor propio. Durante una pausa, `is_music` es falso y `artwork_file` queda vacío. El logo puede mostrarse como identidad visual sin incorporarse al historial musical.

Para una **canción real sin portada**, se utiliza el logo configurado como imagen de respaldo y se conservan su artista y título reales. Esto funciona en la ventana, el reproductor propio y la URL opcional para destinos Icecast-KH compatibles. La API de títulos de AzuraCast no permite cargar esa imagen: su logo y búsqueda de portadas se configuran en su panel.

Enviar un vaciado y dejar de enviar actualizaciones son operaciones distintas: dejar de actualizar puede mantener la canción anterior. El manual de RadioCaster no garantiza el tratamiento de un archivo vacío. Hay que comprobarlo en tu versión. Icecast admite actualizaciones del título, pero no incluye una orden universal para excluir entradas del historial de otros servicios. AzuraCast, Liquidsoap y cada reproductor pueden aplicar caché, datos de respaldo o mostrar la última canción; **no se garantiza controlar sus historiales desde esta app**. No se modificó la estación real para verificarlo.

## Claves dentro de la app

Introduce las claves en sus formularios de Conexiones o Ajustes; **Mostrar/Ocultar** permite revisar la clave y **Borrar** la elimina al guardar. Cancelar descarta los cambios. Las pruebas de conexión son de lectura: no publican títulos ni suben archivos, y no demuestran permisos de escritura.

Las claves se guardan en el **Administrador de credenciales de tu usuario de Windows**, mediante `keyring` y su backend Windows explícito. No se incluyen en `config.json`, registros, archivos públicos ni exportaciones CSV. No hay un respaldo de contraseñas en texto plano. En demostración son temporales.

Los perfiles se separan por carpeta de datos y por dirección/usuario de conexión; al cambiar esos datos o mover la carpeta debes introducir la clave correspondiente. Copiar el repositorio o generar un EXE no copia tus claves. En una PC o usuario diferente se vuelven a introducir. Los fallos de guardado compensan los cambios de claves y mantienen abierta la ventana de ajustes.

Por compatibilidad se siguen leyendo las variables de entorno de instalaciones anteriores si esa conexión aún no ha sido gestionada desde el formulario. Guardar o borrar una clave desde la app tiene prioridad y desactiva ese respaldo para la conexión. El uso normal no requiere configurar variables de entorno.

## Historial y límites

El historial registra fecha/hora, fuente, artista, título, álbum y año solo de canciones válidas. **Exportar CSV** exporta todo el historial, aunque la tabla muestre las 200 canciones más recientes. Las últimas tres aparecen en Inicio.

La selección se calcula con estado, prioridad, carpetas y exclusiones. No identifica infaliblemente la señal al aire después de la consola ni reconoce acústicamente anuncios. Una publicidad mal etiquetada en una carpeta musical puede pasar los filtros: corrige su clasificación y activa Pausar metadatos antes del bloque.

Las consultas ocurren cada dos segundos por defecto. Hay latencia de detección y de servidor. Si el proceso termina abruptamente, el disco falla o el servidor está desconectado, el destino puede conservar el último título. La aplicación no controla la reproducción de RadioBOSS/Spotify ni reconecta el audio.

## Salidas y conexiones opcionales

Además del TXT, se generan XML, JSON, imágenes y un reproductor HTML. Se conservan álbum, año, género, ISRC, duración y progreso cuando la fuente los entregue, sin inventar valores.

- **Ajustes → Carátulas** habilita la vista local, limitada a esta computadora. El botón Ver carátulas la abre; el audio requiere pulsar Play.
- El alojamiento WebDAV opcional publica imágenes y JSON en una carpeta HTTPS existente con lectura pública. No sustituye una configuración de portadas de AzuraCast.
- **Conexiones → AzuraCast** permite monitorear datos públicos y habilitar una salida directa opcional de artista/título con clave API.
- **Ajustes → Icecast directo** permite agregar destinos con formularios y claves en la app. Su consulta de estadísticas es pública y no verifica la contraseña ni permisos de publicación.

Usa una sola ruta de publicación por destino para evitar que RadioCaster, Liquidsoap y la app sobrescriban sus títulos. Los encoders de Zeno.fm permanecen en RadioCaster.

Consulta [Conexiones](docs/CONEXIONES.md), [Integraciones documentadas](docs/INTEGRACIONES.md), [Novedades 0.3](docs/NOVEDADES-0.3.md) y [Validación](docs/VALIDACION.md). La [investigación original](outputs/Investigacion-RadioCaster-Icecast-AzuraCast.md) documenta las capacidades de RadioCaster, Icecast y AzuraCast.

## Datos y arquitectura

La carpeta predeterminada es `%LOCALAPPDATA%\RadioMetadataManager`. La opción `--data-dir C:\ruta` permite cambiarla; contiene configuración, historial SQLite, registros rotativos y salidas. Las claves viven aparte en Windows. Los nombres de imágenes dependen de su contenido; la caché local conserva aproximadamente 40 imágenes además de las actuales.

| Módulo | Responsabilidad |
| --- | --- |
| `sources.py`, `model.py` | Lecturas de fuentes, selección y exclusiones |
| `outputs.py` | Exportación y publicación opcional |
| `remote.py`, `webserver.py`, `player.py` | Monitoreo público y reproductor |
| `engine.py`, `storage.py` | Ciclo de trabajo e historial |
| `config.py`, `credentials.py` | Ajustes y claves separadas |
| `gui.py`, `settings.py`, `appearance.py` | Ventana, formularios y apariencia del sistema |
| `connection_tests.py` | Comprobaciones de conexión de lectura |

## Pruebas y futuro EXE

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:RADIO_GUI_TEST = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Las variables anteriores son solo para desarrollar y ejecutar pruebas, no para configurar claves. Las integraciones remotas se prueban con respuestas simuladas. La ejecución nativa de credenciales, tema y conectores Windows debe verificarse en Windows 11.

Construye el ejecutable **en Windows**, con Python 3.11 x64:

```powershell
.\.venv\Scripts\python.exe -m pip install '.[build]'
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name RadioMetadata --collect-submodules winrt --hidden-import keyring.backends.Windows --collect-submodules win32ctypes launcher.py
```

Distribuye la carpeta completa `dist\RadioMetadata`. Prueba primero la demo y después las conexiones en una PC sin Python. El empaquetado WinRT/keyring, la firma y el instalador siguen pendientes de validación en Windows; no se generó un EXE desde macOS.
