@echo off
REM PIPA Heartbeat Runner — Entry point for Windows Task Scheduler (§14.1)
REM Ejecuta un ciclo de heartbeat delegando a agent/main.py
REM Configurar en Task Scheduler: repeticion cada 30 min, 07:00-22:00

cd /d "%~dp0.."
agent\.venv\Scripts\python.exe agent\main.py
