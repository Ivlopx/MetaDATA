@echo off
cd /d "%~dp0"
py -3.11 -m venv .venv
if errorlevel 1 goto fallo
.venv\Scripts\python.exe -m pip install .
if errorlevel 1 goto fallo
echo Instalacion terminada. Ejecuta demo.bat para probar.
pause
exit /b 0
:fallo
echo No se completo la instalacion. Revisa Python 3.11 y tu conexion.
pause
exit /b 1
