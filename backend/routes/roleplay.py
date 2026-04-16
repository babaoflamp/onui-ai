from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import logging
import asyncio

router = APIRouter()
logger = logging.getLogger(__name__)

DATA_PATH = "data/roleplay-scenarios.json"

class ChatRequest(BaseModel):
    scenario_id: str
    messages: List[dict]  # [{"role": "user/assistant", "content": "..."}]

_scenarios_cache: list | None = None

def load_scenarios():
    global _scenarios_cache
    if _scenarios_cache is not None:
        return _scenarios_cache
    if not os.path.exists(DATA_PATH):
        _scenarios_cache = []
        return _scenarios_cache
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        _scenarios_cache = json.load(f)
    return _scenarios_cache

@router.get("/roleplay", response_class=HTMLResponse)
async def roleplay_page(request: Request):
    return request.app.state.templates.TemplateResponse(request, "ai-roleplay.html")

@router.get("/api/roleplay/scenarios")
async def get_scenarios():
    return load_scenarios()

@router.post("/api/roleplay/chat")
async def roleplay_chat(request: Request, payload: ChatRequest):
    scenarios = load_scenarios()
    scenario = next((s for s in scenarios if s["id"] == payload.scenario_id), None)
    
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    # 역사 인물 롤플레이 프롬프트 구성
    era = scenario.get("era", "")
    speaking_style = scenario.get("speaking_style", "")
    topics = scenario.get("topics") or []
    persona = scenario.get("persona", "역사 인물")
    level = scenario.get("level", "중급")
    goals = scenario.get("goals") or []

    system_prompt = f"""당신은 조선의 임금 세종대왕입니다.
사용자와 대화하기 위해, 완전한 고어체가 아닌 부드러운 옛말 기반의 구어체를 사용합니다.

원칙:
1. 말투: "~하였느니라" 대신 "~하는 것이 좋겠소", "~라 생각하오", "~이 옳다 보오"처럼 부드럽고 자연스럽게 말합니다. "그대", "백성" 등의 표현을 사용합니다. 절대로 '~하였사옵니다'와 같은 신하의 말투는 사용하지 마세요.
2. 사고방식: 항상 실용성과 효율을 우선하며, 이유와 원리를 단계별로 쉽게 풀어 설명합니다.
3. 태도: 따뜻하고 인자하지만 판단은 명확하며, 무지함을 꾸짖기보다 이해시키려 합니다.
4. 표현 스타일: 비유와 예시를 사용하여 쉽게 설명합니다. "내가 살펴보니", "생각건대", "이는 이런 이치이니" 같은 표현을 활용합니다.

지침:
1. 반드시 한국어로만 답변하세요.
2. 답변은 **반드시 3문장 이상**으로 풍부하게 작성하고 절대 문장을 중간에 끊지 마세요.
3. 마지막 문장은 학습자가 대화를 이어갈 수 있도록 열린 질문으로 끝내세요.
4. 학습 목표({', '.join(goals)})를 자연스럽게 달성할 수 있도록 대화를 주도하세요.
5. 학습자가 잘못된 표현을 쓰면 인물의 캐릭터를 유지하며 한 문장으로만 교정해주세요."""

    messages = [{"role": "system", "content": system_prompt}] + payload.messages

    # LLM 호출 (강제로 Ollama 사용)
    backend = "ollama"

    try:
        if backend == "ollama":
            # Ollama 호출 로직
            import requests
            ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
            model = os.getenv("OLLAMA_MODEL", "exaone3.5:7.8b")

            url = f"{ollama_url}/api/generate"
            resp = requests.post(url, json={
                "model": model,
                "prompt": f"{system_prompt}\n\n대화 기록:\n" + "\n".join([f"{m['role']}: {m['content']}" for m in payload.messages]),
                "stream": False,
                "options": {"temperature": 0.7}
            }, timeout=60)

            if resp.status_code != 200:
                raise RuntimeError(f"Ollama 응답 상태 코드: {resp.status_code} - {resp.text}")

            ai_message = resp.json().get("response", "")
        else:
            raise RuntimeError(f"지원되지 않는 AI 백엔드입니다: '{backend}'.")

        return {"message": ai_message}

    except Exception as e:
        logger.error(f"Roleplay chat error (backend={backend}): {e}")
        return JSONResponse(status_code=500, content={"error": str(e), "backend": backend})

@router.post("/api/roleplay/evaluate")
async def roleplay_evaluate(request: Request, payload: ChatRequest):
    scenarios = load_scenarios()
    scenario = next((s for s in scenarios if s["id"] == payload.scenario_id), None)
    
    # 전체 대화 내용을 바탕으로 평가 프롬프트 구성
    chat_log = "\n".join([f"{m['role']}: {m['content']}" for m in payload.messages])
    
    title = scenario.get("title", "") if scenario else ""
    eval_goals = scenario.get("goals") or [] if scenario else []
    keywords = scenario.get("keywords") or [] if scenario else []

    eval_prompt = f"""
    다음은 '{title}' 상황에서의 한국어 대화 기록입니다.
    학습자의 한국어 능력을 평가하고 개선점을 알려주세요.

    대화 기록:
    {chat_log}

    평가 기준:
    1. 목표 달성도: {', '.join(eval_goals)}
    2. 어휘 사용: {', '.join(keywords)} 사용 여부
    3. 문법 및 자연스러움

    결과는 반드시 JSON 형식으로 반환하세요.
    형식: {{"score": 0~100, "feedback": "전체 총평", "strengths": ["장점1", "장점2"], "improvements": ["개선점1", "개선점2"]}}
    """

    # LLM 호출하여 평가 결과 생성
    # (chat API와 유사한 구조로 호출)
    # ... (생략 가능, 구현 시 추가)
    
    return {"status": "success", "result": "Evaluation placeholder"}
