import httpx
import json
import asyncio
import sys
import yaml
import os



# ── 설정 로드 ─────────────────────────────────────────────────
def load_config(path: str = "../env/client.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)

config = load_config()

# ── 설정값 ───────────────────────────────────────────────────
SERVER_URL = config["server"]["url"]

# Windows ANSI 활성화
if sys.platform == "win32":
    os.system("color")

# 색상 직접 선언
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RED = "\033[31m"
RESET = "\033[0m"

# ── 스트리밍 채팅 ─────────────────────────────────────────────
async def stream_chat(user_message: str) -> None:
    payload = {
        "messages": [
            {"role": "user", "content": user_message}
        ]
    }

    prev_was_reasoning = False

    try:
        async with httpx.AsyncClient(
            timeout=config["http_client"]["timeout"]
        ) as client:
            async with client.stream(
                "POST", SERVER_URL, json=payload
            ) as response:

                if response.status_code != 200:
                    print(f"{RED}서버 에러: {response.status_code}{RESET}")
                    return

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue

                    data_str = line[len("data:"):].strip()

                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    if "error" in data:
                        print(f"\n{RED}에러: {data['error']}{RESET}")
                        break

                    delta = data.get("choices", [{}])[0].get("delta", {})
                    reasoning = delta.get("reasoning_content", "")
                    content   = delta.get("content", "")

                    if reasoning:
                        print(f"{MAGENTA}{reasoning}{RESET}",
                              end="", flush=True)
                        prev_was_reasoning = True

                    if content:
                        # reasoning → content 전환시 한 줄 띄움
                        if prev_was_reasoning:
                            print("\n")
                            prev_was_reasoning = False
                        print(f"{BLUE}{content}{RESET}",
                              end="", flush=True)

    except httpx.ConnectError:
        print(f"{RED}서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.{RESET}")
    except httpx.TimeoutException:
        print(f"{RED}요청 시간이 초과되었습니다.{RESET}")
    except KeyboardInterrupt:
        print(f"\n{RED}중단되었습니다.{RESET}")
    finally:
        print()


# ── 실행 ──────────────────────────────────────────────────────
def main():
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = input("질문을 입력하세요: ").strip()
        if not question:
            print("질문을 입력해주세요.")
            return

    asyncio.run(stream_chat(question))


if __name__ == "__main__":
    main()