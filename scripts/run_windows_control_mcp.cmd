@echo off
setlocal
set "PROJECT_ROOT=%~dp0.."
set "PYTHONPATH=%PROJECT_ROOT%\src"
python -m windows_control_mcp.server
exit /b %ERRORLEVEL%
