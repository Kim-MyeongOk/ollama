## 프로젝트 폴더 구조

```
ollama/                          ← 프로젝트 루트
├── env/                         ← 환경 변수 설정 파일
│   ├── server.yaml
│   └── client.yaml
├── src/                         ← 소스 코드
│   ├── server.py
│   └── client.py
├── requirements.txt             ← 패키지 목록
├── run_server.bat               ← 서버 실행
├── run_client.bat               ← 클라이언트 실행
└── read_me.md                   ← 프로젝트 구조 설명
```

## 가상환경

```
C:\Users\{사용자명}\anaconda3\envs\ollama   ← anaconda 가상환경 (프로젝트 외부)
```

## 실행 순서

### 1. 최초 설정 (1회만)
```
setup.bat 더블클릭
→ anaconda 가상환경 활성화
→ requirements.txt 패키지 자동 설치
```

### 2. Ollama 모델 확인
```
cmd 창에서
ollama list
→ qwen3-vl:4b 설치 확인

없으면
ollama pull qwen3-vl:4b
```

### 3. 서버 실행
```
run_server.bat 더블클릭
→ anaconda 가상환경 활성화
→ src/server.py 실행
→ FastAPI 서버 시작 (port: 8000)
```

### 4. 클라이언트 실행
```
run_client.bat 더블클릭 (별도 창)
→ anaconda 가상환경 활성화
→ src/client.py 실행
→ 질문 입력
```

## 파일 설명

| 파일 | 위치 | 설명 |
|------|------|------|
| server.yaml | env/ | FastAPI 서버 환경 설정 (host, port, ollama 설정, http 클라이언트 설정) |
| client.yaml | env/ | 클라이언트 환경 설정 (서버 URL, timeout) |
| server.py | src/ | FastAPI 서버 코드 (Ollama 프록시, 스트리밍 처리) |
| client.py | src/ | 클라이언트 코드 (스트리밍 수신, 색상 출력) |
| requirements.txt | 루트 | 패키지 목록 |
| setup.bat | 루트 | 최초 환경 설정 |
| run_server.bat | 루트 | 서버 실행 |
| run_client.bat | 루트 | 클라이언트 실행 |

## 통신 흐름

```
[client.py]
    ↓ POST /v1/chat/completions (httpx)
[server.py - FastAPI :8000]
    ↓ CustomChatOpenAI.astream()
[Ollama :11434]
    ↓
[qwen3-vl:4b 모델]
    ↓
스트리밍 응답 역순으로 반환
    ↓
reasoning_content → MAGENTA 출력
content           → BLUE 출력
```

## 환경 설정

| 항목 | 값 |
|------|-----|
| Python | anaconda 가상환경 (ollama) |
| 서버 포트 | 8000 |
| Ollama 포트 | 11434 |
| 모델 | qwen3-vl:4b |
| 타임아웃 | 120초 |