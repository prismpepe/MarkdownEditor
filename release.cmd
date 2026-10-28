@echo off
rem Build the exe and make the distribution zip.
rem   release.cmd           run build.cmd (tests + exe), then make dist\MarkdownEditor_YYYYMMDD.zip
rem   release.cmd nobuild   make the zip from the existing dist\MarkdownEditor.exe
setlocal
cd /d "%~dp0"
echo Working folder: %CD%
echo.

if /i "%~1"=="nobuild" goto :zip

echo [1/4] Checking vendor files...
for %%F in (mermaid vega vega-lite vega-embed) do call :need "vendor\%%F.min.js"
if defined MISSING goto :fail

echo [2/4] Removing the old exe...
if not exist "dist\MarkdownEditor.exe" goto :build
tasklist /fi "imagename eq MarkdownEditor.exe" 2>nul | find /i "MarkdownEditor.exe" >nul
if not errorlevel 1 call :askclose
set "TRY=0"
:delloop
attrib -r -s -h "dist\MarkdownEditor.exe" >nul 2>&1
del /q "dist\MarkdownEditor.exe" >nul 2>&1
if not exist "dist\MarkdownEditor.exe" goto :build
set /a TRY+=1
if %TRY% GEQ 3 goto :locked
rem wait 2 seconds (virus scanners may be holding the file), then retry
ping -n 3 127.0.0.1 >nul
goto :delloop

:build
echo [3/4] Running the tests and building the exe with build.cmd ^(this takes a few minutes^)...
call build.cmd
if not exist "dist\MarkdownEditor.exe" goto :nobuilt

:zip
echo [4/4] Making the zip...
if not exist "dist\MarkdownEditor.exe" goto :noexe
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" tools\make_release.py
if errorlevel 1 goto :fail
echo.
echo Done. The zip is in the dist folder.
goto :end

:need
if exist %1 goto :eof
echo [ERROR] %~1 not found.
set "MISSING=1"
goto :eof

:askclose
echo MarkdownEditor.exe is running. Save your work and close it before the build.
echo ^(It is not closed automatically, so that unsaved text is never lost.^)
pause
goto :eof

:locked
echo [ERROR] Cannot delete dist\MarkdownEditor.exe.
echo   - Is the editor still running? Check Task Manager for MarkdownEditor.exe.
echo   - Is a virus scanner or an Explorer preview using the file? Wait a moment and try again.
goto :fail

:nobuilt
echo [ERROR] Tests or build failed: dist\MarkdownEditor.exe was not created. See the messages above.
goto :fail

:noexe
echo [ERROR] dist\MarkdownEditor.exe not found. Run release.cmd without "nobuild".
goto :fail

:fail
echo.
echo Release FAILED.

:end
echo.
pause
endlocal
