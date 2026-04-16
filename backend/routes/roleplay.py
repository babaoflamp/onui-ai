from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import re
import logging
import asyncio
import requests

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

    system_prompt = f"""당신은 {era}의 인물 {persona}입니다.
{speaking_style}을(를) 사용하여 사용자와 자연스럽게 대화하세요.

원칙:
1. 말투: {speaking_style}에 충실하게 대화합니다. {persona}의 시대적 배경과 지위를 고려하여 적절한 호칭과 어투를 사용하세요.
2. 사고방식: {persona}의 실제 역사적 행보와 철학에 기반하여 답변하세요.
3. 태도: 학습자에게 친절하고 교육적인 태도를 유지하되, 인물의 고유한 성격(예: 세종의 인자함, 이순신의 단호함)을 잃지 마세요.
4. 주제: 주로 {', '.join(topics)}에 대해 대화하며, 관련 지식을 자연스럽게 전달하세요.

지침:
1. 반드시 한국어로만 답변하세요.
2. **중요: 모든 답변은 반드시 3문장 이상 5문장 이하로 작성하세요.** 풍부한 배경 설명과 구체적인 예시를 포함하여 학습자가 충분한 한국어 문장을 접하게 하세요. 절대 한 문장으로 짧게 답하지 마세요.
3. 마지막 문장은 항상 학습자가 대화를 이어갈 수 있도록 하는 질문으로 마무리하세요.
4. 학습 목표({', '.join(goals)})를 자연스럽게 달성할 수 있도록 대화를 주도하세요.
5. 학습자가 문법이나 표현을 틀리면 캐릭터를 유지하며 한 문장 이내로 부드럽게 교정해 주세요."""

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
    model_backend = os.getenv("MODEL_BACKEND", "ollama")

    try:
        raw_output = ""

        if model_backend == "gemini":
            from google import genai as genai_lib
            gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            if not gemini_key:
                raise RuntimeError("Gemini API key not configured")
            gc = genai_lib.Client(api_key=gemini_key)
            resp = gc.models.generate_content(model=gemini_model, contents=eval_prompt)
            raw_output = resp.text or ""

        elif model_backend == "openai":
            from openai import OpenAI as _OpenAI
            openai_key = os.getenv("OPENAI_API_KEY")
            openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            if not openai_key:
                raise RuntimeError("OpenAI API key not configured")
            oc = _OpenAI(api_key=openai_key)
            resp = oc.chat.completions.create(
                model=openai_model,
                messages=[{"role": "user", "content": eval_prompt}],
                temperature=0.5,
            )
            raw_output = resp.choices[0].message.content or ""

        else:  # ollama
            ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
            ollama_model = os.getenv("OLLAMA_MODEL", "exaone3.5:2.4b")
            resp = requests.post(
                f"{ollama_url}/api/generate",
                json={"model": ollama_model, "prompt": eval_prompt, "stream": False, "options": {"temperature": 0.5}},
                timeout=60,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text}")
            raw_output = resp.json().get("response", "")

        # JSON 파싱: 코드 펜스 또는 중괄호 블록 추출
        parsed = None
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_output, re.IGNORECASE)
        if fence:
            try:
                parsed = json.loads(fence.group(1).strip())
            except Exception:
                pass
        if parsed is None:
            brace = re.search(r"(\{[\s\S]*\})", raw_output)
            if brace:
                try:
                    parsed = json.loads(brace.group(1))
                except Exception:
                    pass

        if parsed is None or not isinstance(parsed, dict):
            raise RuntimeError("LLM이 유효한 JSON을 반환하지 않았습니다.")

        # 필수 필드 보정
        result = {
            "score": int(parsed.get("score", 0)),
            "feedback": parsed.get("feedback", ""),
            "strengths": parsed.get("strengths", []),
            "improvements": parsed.get("improvements", []),
        }
        return {"status": "success", "result": result}

    except Exception as e:
        logger.error(f"Roleplay evaluate error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
