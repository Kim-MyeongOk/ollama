@echo off

:: 프로젝트 경로는 bat 파일 기준으로 자동
cd /d %~dp0

:: 가상환경 활성화
call C:\Users\kmo97\anaconda3\Scripts\activate.bat
call conda activate ollama

:: 패키지 설치 확인
pip install -r requirements.txt

:: 서버 실행
cd src
python server.py

pause