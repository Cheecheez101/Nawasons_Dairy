@echo off
REM Run Django manage.py using the project's virtualenv Python
"%~dp0.venv\Scripts\python.exe" "%~dp0manage.py" %*
