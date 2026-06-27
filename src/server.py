import json
import traceback
import httpx
import logging
import uvicorn
from contextlib              import asynccontextmanager
from fastapi                 import FastAPI, Request, HTTPException
from fastapi.responses       import StreamingResponse
from fastapi.openapi.utils   import get_openapi
from langchain_openai        import ChatOpenAI
from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage, BaseMessage
from langchain_core.outputs  import ChatGenerationChunk
from typing import AsyncIterator
from typing import Dict
from typing import List
from config import cfg
from config import logging as logger
from openai import APIConnectionError

# 대화 이력 저장소 (실무에서는 Redis나 RDB 사용 권장)
# 구조: { session_id: [{"role": "user/assistant/system", "content": "...", "reasoning_content": "..."}] }
chat_histories: Dict[str, List[Dict[str, str]]] = {}


# ── 싱글톤 커넥션 풀 ──────────────────────────────────────────
_http_client: httpx.AsyncClient | None = None

def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        http_client = cfg.http_client
        _http_client = httpx.AsyncClient(
            limits = httpx.Limits(
                max_connections           = http_client.max_connections,
                max_keepalive_connections = http_client.max_keepalive_connections,
                keepalive_expiry          = http_client.keepalive_expiry
            ),
            timeout = httpx.Timeout(
                connect = http_client.timeout.connect,
                read    = http_client.timeout.read,
                write   = http_client.timeout.write,
                pool    = http_client.timeout.pool
            ),
            verify   = http_client.verify,
            trust_env= http_client.trust_env
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

app = FastAPI(lifespan = lifespan)


# ── ChatOpenAI 상속 - reasoning_content 처리 ─────────────────
class CustomChatOpenAI(ChatOpenAI):

    def _convert_chunk_to_generation_chunk(
        self,
        chunk                : dict,
        default_chunk_class  : type,
        base_generation_info : dict | None = None,
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
    model_info = cfg.ollama
    return CustomChatOpenAI(
        model             = model_info.model,
        base_url          = model_info.base_url,
        api_key           = model_info.api_key,
        streaming         = model_info.streaming,
        timeout           = model_info.timeout,
        http_async_client = get_http_client(),
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

    session_id = request.headers.get("X-Session-ID")
    incoming_messages = body.get("messages", [])

    if not incoming_messages:
        raise HTTPException(status_code=400, detail="messages 필드가 비어있습니다")

    if session_id:
        if session_id not in chat_histories:
            # 처음 연결된 세션이라면 현재 들어온 메시지 전체로 초기화 (시스템 프롬프트 등 포함 가능)
            chat_histories[session_id] = incoming_messages
        else:
            # 기존 이력이 있다면, 클라이언트가 보낸 '마지막 유저 메시지'만 기존 이력에 누적
            # (프론트엔드가 이전 대화를 다 보낼 필요 없이 새 질문만 보내도 됨)
            last_user_message = incoming_messages[-1]
            chat_histories[session_id].append(last_user_message)

        # LLM에 전달할 최종 메시지 리스트는 '누적된 전체 대화 이력'이 됩니다.
        target_messages = chat_histories[session_id]
    else:
        # session_id가 없으면 일반적인 1회성 대화로 처리
        target_messages = incoming_messages

    try:
        # LangChain Message 객체로 변환 (기존 함수 활용)
        message_list = parse_messages(target_messages)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


    async def generate() -> AsyncIterator[str]:
        try:
            final_message = None
            accumulated_reasoning = ""
            accumulated_content = ""  # AI 답변 저장을 위해 content도 누적

            async for chunk in llm.astream(message_list):
                if final_message is None:
                    final_message = chunk
                else:
                    final_message += chunk

                reasoning = chunk.additional_kwargs.get("reasoning_content", "")
                content = chunk.content or ""

                if reasoning:
                    accumulated_reasoning += reasoning
                if content:
                    accumulated_content += content

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

            # 스트리밍이 성공적으로 끝나면 모델 추론을 해당 세션 이력에 저장
            if session_id and (accumulated_content or accumulated_reasoning):
                ai_message_history = {
                    "role": "assistant",
                    "content": accumulated_content
                }
                # Reasoning(생각 과정) 데이터가 존재한다면 이력에도 포함
                if accumulated_reasoning:
                    ai_message_history["reasoning_content"] = accumulated_reasoning

                chat_histories[session_id].append(ai_message_history)
        except Exception as exception:
            if type(exception) == APIConnectionError:
                result_data = f"data: {json.dumps({'error': '503, APIConnectionError'})}\n\n"
            else:
                result_data = f"data: {json.dumps({'error': str(exception)})}\n\n"
            logger.error(f"스트리밍 중 에러: {exception}")
            if session_id and session_id in chat_histories and chat_histories[session_id]:
                chat_histories[session_id].pop()
            yield result_data
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


llm = make_llm()
# ── 실행 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    server_info = cfg.server
    uvicorn.run(
        app        = "server:app",
        host       = server_info.host,
        port       = server_info.port,
        reload     = server_info.reload,
        log_config = cfg.unicorn_logging,
        workers    = server_info.workers
    )