@echo off
echo =========================================
echo       Iniciando Simulador NTN...
echo =========================================
echo.
echo Arrancando el servidor local...
echo La ventana de la aplicacion se abrira en unos segundos.
echo.

:: Iniciar streamlit en segundo plano de forma silenciosa
start /B streamlit run src/streamlit_app.py --server.headless true > NUL 2>&1

:: Esperar 5 segundos para que el servidor este listo
timeout /t 5 /nobreak > NUL

:: Intentar abrir en modo App usando Edge (nativo en Windows) o Chrome
start msedge --app=http://localhost:8501
if %ERRORLEVEL% neq 0 start chrome --app=http://localhost:8501

echo.
echo Si has cerrado la ventana por error, puedes volver a abrirla
echo abriendo tu navegador en: http://localhost:8501
echo.
echo [ PARA APAGAR EL SIMULADOR, CIERRA ESTA VENTANA NEGRA ]
echo.
pause
