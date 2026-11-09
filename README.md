# MetaDATA · versión 0.2.1

Aplicación de escritorio en español para Windows 11, Python 3.11 y PySide6. Administra **metadatos**; el audio continúa por Windows → FXSound → consola → USB → RadioCaster. No modifica ese recorrido.

Investigación ampliada con comprobaciones públicas de ORO FM: [capacidades de RadioCaster, Icecast y AzuraCast](outputs/Investigacion-RadioCaster-Icecast-AzuraCast.md). Incluye las vías de carátulas y los límites de la API. La adaptación implementada se describe en [Novedades 0.2](docs/NOVEDADES-0.2.md).

Incluye ventana, bandeja, ocultar/restaurar, selección automática o manual, mensaje de estación, carátula disponible, ajustes persistentes, historial SQLite y registros con rotación. La fuente seleccionada se estima por reproducción y prioridad; no demuestra qué señal dejó pasar la consola.

## Probar sin conexiones

Descomprime el proyecto en Windows 11. Instala Python **3.11 de 64 bits** desde [python.org](https://www.python.org/downloads/windows/). En PowerShell, dentro de esta carpeta:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m radio_metadata --demo
```

También puedes ejecutar `instalar.bat` y luego `demo.bat`. La demo permite probar RadioBOSS, Spotify, ambas fuentes, anuncio y silencio. Usa datos inventados, historial separado y `demo-output`; **no la conectes a RadioCaster al aire**. Nunca publica a servidores.

Para fuentes reales:

```powershell
.\.venv\Scripts\python.exe -m radio_metadata
```

O ejecuta `iniciar.bat`. Si vienes de la versión anterior, vuelve a ejecutar `instalar.bat`: la configuración y el historial se migran al iniciar. Tras editar el código, reinstala con `pip install .`; para desarrollo usa `pip install -e .`.

`examples/orofm.config.json` es una configuración completa de referencia, con publicación y monitoreo desactivados. Úsala solo al crear una carpeta de datos nueva; no sobrescribas una configuración personalizada.

## Primera configuración real

1. Abre **Ajustes → Estación**: nombre, eslogan, descripción, web, mensajes de pausa/sin música y logo opcional. Los mensajes son textos literales; el cambio de nombre no reescribe automáticamente tus mensajes.
2. En RadioBOSS activa su API, restringida a localhost, y configura contraseña/usuario con permisos de lectura. En Ajustes → Fuentes habilita RadioBOSS y su URL. Antes de iniciar la app, define la contraseña localmente:

   ```powershell
   $env:RADIOBOSS_PASSWORD = 'tu contraseña local'
   .\.venv\Scripts\python.exe -m radio_metadata
   ```

   La contraseña no se guarda en `config.json`. La variable se hereda al iniciar el proceso; si la cambias, reinicia la app. No publiques capturas de credenciales ni las envíes al chat.
3. En **Música y exclusiones** agrega solo carpetas de canciones. Mantén anuncios/promos/jingles fuera de ellas, agrega sus carpetas a exclusiones y comprueba sus tipos en RadioBOSS. Sin carpetas aprobadas se publica el mensaje de estación. No se deducen artista/título del nombre del archivo.
4. Spotify usa las sesiones multimedia de Windows (SMTC), sin OAuth ni credenciales. Si Spotify no expone sesión, estado, artista, título o tipo musical suficiente, no se inventan datos. Empieza en **observación**: revisa Estado de fuentes. Activa su participación solo después de verificar comportamiento y condiciones de uso. La [política de Spotify](https://developer.spotify.com/documentation/web-api/reference/get-the-users-currently-playing-track) indica que su plataforma no permite radiodifusión no interactiva; este proyecto no concede derechos de retransmisión.
5. En RadioCaster → Settings → Metadata elige **Read from file** y apunta al archivo que indica la app, normalmente:

   ```text
   %LOCALAPPDATA%\RadioMetadataManager\output\nowplaying.txt
   ```

   Selecciona primera línea y UTF-8 (o verifica Auto con acentos). RadioCaster mantiene sus conexiones existentes hacia AzuraCast y el destino secundario. Comprueba el título en ambos reproductores después de su latencia. Este método está [documentado por DJSoft](https://manual.djsoft.net/radiocaster/en/metadata.html).
6. Si ambas apps reproducen, usa la prioridad configurada o **Solo RadioBOSS / Solo Spotify**. El modo manual no cambia automáticamente a otra app si la elegida se pausa. **Mensaje de estación** cubre anuncios, micrófono o cambios físicos de consola. Para volver, selecciona Automático.

Cerrar con X oculta si existe bandeja; restaura desde su icono. **Salir** termina el proceso y escribe el mensaje sin música. Sin bandeja, Ocultar minimiza y X sale. No hay autoarranque del administrador en esta versión: puedes añadir un acceso directo a `iniciar.bat` en `shell:startup` después de validar la instalación.

## Protección de títulos e historial

La política elige primero la fuente y después clasifica su contenido. Un anuncio de RadioBOSS no permite mostrar la canción de Spotify por debajo. Solo una canción seleccionada con artista/título válidos, carpeta aprobada en RadioBOSS, sin reglas de exclusión y sin error entra al historial. Los cambios de fuente, pausa o mensaje separan reproducciones. Una canción repetida sin pausa ni cambio de metadatos puede contarse una sola vez; el historial representa selecciones observadas, no detección acústica ni una auditoría de emisión.

No existe clasificación infalible de anuncios solo con estos metadatos. Un anuncio etiquetado como canción dentro de una carpeta musical podría pasar; corrige su tipo/carpeta y usa Mensaje de estación. Las reglas excluyen términos completos o frases, sin distinguir mayúsculas; los tipos se comparan por coincidencia parcial. Spotify exige tipo musical reportado por Windows y autorización de publicación en ajustes; esto tampoco prueba que no sea un anuncio.

Las lecturas se hacen cada 2 segundos por defecto, con límites de espera. Hay latencia entre el cambio real y la actualización: activa el mensaje **antes** de lanzar un anuncio para evitar títulos transitorios. Un fallo de fuente produce mensaje de estación en la siguiente evaluación. Si el proceso muere, el disco no permite escribir o el servidor está desconectado, el destino puede conservar el último título. Supervisa el estado y evita otros escritores de metadatos para ese mismo destino.

## Carátulas y servicios

Se intenta leer imagen de RadioBOSS vía `readtag` y de Spotify vía miniatura SMTC. Se conserva también álbum, artista del álbum, año, género, ISRC y duración/progreso **cuando la fuente los entregue**; no se inventan campos ausentes. La ventana muestra álbum/año/género/duración, y el historial conserva los datos de la canción seleccionada.

Además de `nowplaying.txt`, se generan `nowplaying.xml`, `nowplaying.json`, imágenes PNG/JPEG/WebP y `player.html`. El XML permite plantillas de RadioCaster, pero no convierte sus atributos en campos independientes del stream. El JSON público no contiene rutas de música, credenciales ni títulos de anuncios excluidos.

En **Ajustes → Carátulas y reproductor** puedes habilitar una vista local. Pulsa **Ver carátulas** para abrirla. Utiliza la portada de la canción o el logo de estación en pausas; si los datos dejan de actualizarse, oculta los datos musicales. El servicio escucha únicamente en `127.0.0.1` y permite leer TXT/JSON/XML e imágenes, nunca la configuración o el historial.

La subida opcional a un alojamiento WebDAV HTTPS publica las imágenes exactas, el reproductor y JSON. Requiere una carpeta de subida y una URL pública compatibles; no basta con indicar el dominio de AzuraCast. El conector Icecast-KH puede enviar esa URL mediante `StreamUrl` cuando se configura expresamente. Esto **no actualiza automáticamente `song.art` en AzuraCast** ni garantiza compatibilidad de cualquier reproductor. Consulta [Conexiones](docs/CONEXIONES.md).

En **Ajustes → AzuraCast y monitoreo** se pueden comprobar título, álbum e imagen que informa ORO FM, y el estado de su mount Icecast. Las consultas son de lectura y no intervienen en la selección ni en el historial. Muestran coincidencias/diferencias con la última consulta, con su fecha; puede existir retardo. Las direcciones e ID 2 de ORO FM están precargados, pero la comprobación comienza desactivada.

La publicación directa por API AzuraCast es otra opción desactivada inicialmente. Solo envía artista y título: la API investigada filtra álbum/imagen. Las carátulas automáticas de AzuraCast se configuran desde su panel; la app incluye una guía. Para límites y fuentes documentales lee [Integraciones](docs/INTEGRACIONES.md).

El destino secundario es **Zeno.fm**, confirmado por el usuario. La ruta inicial es RadioCaster → Zeno.fm mediante los datos de conexión de su panel. La compatibilidad de títulos y carátulas debe comprobarse por separado.

## Datos y arquitectura

Carpeta predeterminada `%LOCALAPPDATA%\RadioMetadataManager`; `--data-dir C:\ruta` permite cambiarla. Contiene `config.json`, `history.sqlite3`, `app.log` (1 MB × 4) y `output/`. Guarda copia de configuración e historial para respaldos; no distribuyas datos personales de tu instalación. `nowplaying.txt` y JSON se reemplazan atómicamente por separado; JSON referencia su propia imagen por nombre. La caché local conserva aproximadamente 40 imágenes, además de las que estén en uso. La caché del alojamiento requiere una política de limpieza propia.

| Módulo | Responsabilidad |
| --- | --- |
| `sources.py` | Contrato Source, API RadioBOSS, sesiones Spotify/Windows, demo |
| `model.py` | Selección, validación de canciones y exclusiones |
| `outputs.py` | TXT/XML/JSON e imágenes, Icecast-KH, AzuraCast textual y WebDAV opcionales |
| `remote.py` | Observación pública AzuraCast/Icecast y comparación de títulos |
| `webserver.py`, `player.py` | Servicio de lectura local y reproductor con caducidad de metadatos |
| `engine.py` | Consultas concurrentes, política, historial y publicación |
| `storage.py` | SQLite y separación de reproducciones |
| `config.py` | Configuración validada y escritura atómica |
| `gui.py` | PySide6, bandeja, ajustes y trabajador fuera del hilo visual |

Para agregar una app implementa `Source.poll()` asíncrono con Snapshot y regístrala en `make_sources`; añade su criterio de clasificación en `valid_music` y ajustes. Los conectores no controlan reproducción de RadioBOSS/Spotify; los controles actuales administran selección/publicación. No hay reconocimiento acústico, OAuth Spotify, carga de portada arbitraria en la API de AzuraCast, retardo ajustable por destino ni reconexión del audio. El AutoDJ, grabaciones, relays y búsqueda de carátulas se configuran en el panel de AzuraCast; no se modifican desde esta app.

## Pruebas

Si Spotify muestra `ModuleNotFoundError`, cierra MetaDATA desde **Salir**, ejecuta `git pull` y después `instalar.bat`. La versión 0.2.1 agrega los paquetes base `winrt-Windows.Foundation` y `winrt-Windows.Foundation.Collections`, que PyWinRT 3.2.1 no instala automáticamente con los paquetes de Media. Si falta otro componente WinRT, el estado de la fuente muestra su nombre para diagnosticarlo. [Dependencias modulares de PyWinRT](https://pywinrt.readthedocs.io/en/latest/installing/).

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:QT_QPA_PLATFORM = 'offscreen'
$env:RADIO_GUI_TEST = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Las pruebas cubren prioridad, anuncios, datos incompletos, carpetas, historial, UTF-8, errores Icecast, respuestas XML maliciosas, cambios de pista y demo sin red; la prueba visual recorre selección y ajustes. La configuración v1 se migra con copia de respaldo; el historial se amplía sin borrar filas. La validación de entrega y las pruebas pendientes en Windows están en [docs/VALIDACION.md](docs/VALIDACION.md).

## Futuro EXE

Construye **en Windows 11**, desde la misma carpeta y con Python 3.11 x64:

```powershell
.\.venv\Scripts\python.exe -m pip install '.[build]'
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name RadioMetadata --collect-submodules winrt launcher.py
```

El resultado estará en `dist\RadioMetadata\RadioMetadata.exe`; distribuye la carpeta completa. Primero prueba `--demo` y después los conectores reales en una PC sin Python. Falta comprobar empaquetado WinRT, firma del ejecutable y una distribución instalable. No se ha generado un EXE Windows en este entorno macOS.
