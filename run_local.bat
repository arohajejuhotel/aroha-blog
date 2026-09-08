@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist ".env" (
  echo .env 파일이 없습니다. .env.example 를 복사해서 값을 채우세요.
  pause & exit /b 1
)
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
python -m src.publish %*
pause
