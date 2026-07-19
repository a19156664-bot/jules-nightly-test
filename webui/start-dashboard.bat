@echo off
cd /d "%~dp0.."
start http://127.0.0.1:8000/
"C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn webui.app:app --port 8000