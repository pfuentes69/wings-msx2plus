@echo off
setlocal
cd /d "%~dp0"
if not exist MSXgl\projects mkdir MSXgl\projects
MSXgl\tools\build\Node\node.exe MSXgl\engine\script\js\build.js %*
exit /b %errorlevel%
