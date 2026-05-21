@echo off

:: 프로젝트 경로로 이동
cd /d %~dp0

:: anaconda 가상환경 활성화
call C:\Users\kmo97\anaconda3\Scripts\activate.bat
call conda activate ollama

:: src 폴더로 이동 후 실행
cd src
python client.py

pause