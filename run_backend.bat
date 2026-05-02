@echo off
cd /d "D:\my bus\backend"
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
