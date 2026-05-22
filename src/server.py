import json
import httpx
import logging
import uvicorn
import yaml
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage, BaseMessage
from langchain_core.outputs import ChatGenerationChunk
from typing import AsyncIterator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── 설정 로드 ─────────────────────────────────────────────────
def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)

yaml_path = "../env/server.yaml"
config = load_config(yaml_path)


# ── 싱글톤 커넥션 풀 ──────────────────────────────────────────
_http_client: httpx.AsyncClient | None = None

def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        hc = config["http_client"]
        _http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=hc["max_connections"],
                max_keepalive_connections=hc["max_keepalive_connections"],
                keepalive_expiry=hc["keepalive_expiry"]
            ),
            timeout=httpx.Timeout(
                connect=hc["timeout"]["connect"],
                read=hc["timeout"]["read"],
                write=hc["timeout"]["write"],
                pool=hc["timeout"]["pool"]
            ),
            verify=hc["verify"],
            trust_env=hc["trust_env"]
        )
        logger.info("HTTP 커넥션 풀 생성됨")
    return _http_client


# ── lifespan ─────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    global _http_client
    if _http_client:
        await _http_client.aclose()
        logger.info("HTTP 커넥션 풀 종료됨")

app = FastAPI(lifespan=lifespan)


# ── ChatOpenAI 상속 - reasoning_content 처리 ─────────────────
class CustomChatOpenAI(ChatOpenAI):

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None = None,
    ) -> ChatGenerationChunk | None:

        gen_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )

        if gen_chunk is not None:
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            reasoning = delta.get("reasoning", "")
            delta["reasoning_content"] = reasoning

            if isinstance(gen_chunk.message, AIMessageChunk):
                gen_chunk.message.additional_kwargs["reasoning_content"] = reasoning

        return gen_chunk


# ── LLM 인스턴스 생성 ─────────────────────────────────────────
def make_llm() -> CustomChatOpenAI:
    ol = config["ollama"]
    return CustomChatOpenAI(
        model=ol["model"],
        base_url=ol["base_url"],
        api_key=ol["api_key"],
        streaming=ol["streaming"],
        timeout=ol["timeout"],
        http_async_client=get_http_client(),
    )


# ── 메시지 변환 ───────────────────────────────────────────────
def parse_messages(messages_raw: list) -> list[BaseMessage]:
    result = []
    for m in messages_raw:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "user":
            result.append(HumanMessage(content=content))
    if not result:
        raise ValueError("유효한 메시지가 없습니다")
    return result


# ── /v1/chat/completions ──────────────────────────────────────
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="잘못된 JSON 형식입니다")

    try:
        message_list = parse_messages(body.get("messages", []))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    llm = make_llm()

    async def generate() -> AsyncIterator[str]:
        try:
            final_message = None
            accumulated_reasoning = ""  # reasoning 별도 누적

            async for chunk in llm.astream(message_list):

                # 디버그 로그
                # logger.info(f"chunk.content: {repr(chunk.content)}")
                # logger.info(f"chunk.additional_kwargs: {chunk.additional_kwargs}")

                # 청크 누적
                if final_message is None:
                    final_message = chunk
                else:
                    final_message += chunk

                reasoning = chunk.additional_kwargs.get("reasoning_content", "")
                content = chunk.content or ""

                # reasoning 별도 누적
                if reasoning:
                    accumulated_reasoning += reasoning

                if not reasoning and not content:
                    continue

                payload = {
                    "choices": [{
                        "delta": {
                            "reasoning_content": reasoning,
                            "content": content
                        }
                    }]
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            # 스트리밍 완료 후 final_message에 누적된 reasoning 반영
            if final_message and accumulated_reasoning:
                final_message.additional_kwargs["reasoning_content"] = accumulated_reasoning

            # logger.info(f"최종 누적 content: {final_message.content if final_message else None}")
            # logger.info(f"최종 누적 reasoning: {accumulated_reasoning[:50] if accumulated_reasoning else None}")

        except Exception as e:
            logger.error(f"스트리밍 중 에러: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


# ── 헬스체크 ──────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


# ── 실행 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    sv = config["server"]
    uvicorn.run(
        app="server:app",
        host=sv["host"],
        port=sv["port"],
        reload=sv["reload"]
    )