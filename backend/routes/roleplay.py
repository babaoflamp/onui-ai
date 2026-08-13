from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator
from typing import List, Literal
from uuid import uuid4
import json
import sqlite3
import os
import re
import logging
import asyncio
import requests

from backend.database import connect
from backend.routes.deps import (
    get_current_user, check_and_consume_credits, refund_consumed_credits, romanize_korean,
)

router = APIRouter()
logger = logging.getLogger(__name__)

DATA_PATH = "data/roleplay-scenarios.json"

MAX_MESSAGES = 20
MAX_MESSAGE_LENGTH = 2000


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class ChatRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=100)
    messages: List[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)


class CustomScenarioRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=300)
    level: str = Field(default="B1", min_length=1, max_length=30)
    initial_message: str = Field(min_length=1, max_length=1000)
    persona: str = Field(default="대화 상대", min_length=1, max_length=100)
    era: str = Field(default="현대", min_length=1, max_length=150)
    speaking_style: str = Field(default="친절하고 자연스러운 말투", min_length=1, max_length=200)
    topics: List[str] = Field(default_factory=list, max_length=8)
    goals: List[str] = Field(default_factory=list, max_length=8)
    keywords: List[str] = Field(default_factory=list, max_length=8)
    tts_voice: Literal["Kore", "Charon", "Orus", "Aoede", "Puck"] = "Kore"
    image: str | None = Field(default=None, max_length=500)

    @field_validator("topics", "goals", "keywords")
    @classmethod
    def validate_list_items(cls, values):
        cleaned = [value.strip() for value in values if value.strip()]
        if any(len(value) > 100 for value in cleaned):
            raise ValueError("List items must be 100 characters or fewer")
        return cleaned


class CustomScenarioUpdate(CustomScenarioRequest):
    pass


class CustomScenarioReorderRequest(BaseModel):
    scenario_ids: List[str] = Field(max_length=100)


def _validate_history(messages: list[ChatMessage], *, require_user_turn: bool = False) -> None:
    """Ensure the browser cannot submit an arbitrary or malformed transcript."""
    if messages[0].role != "assistant":
        raise HTTPException(status_code=422, detail="Conversation must start with an assistant message")
    for previous, current in zip(messages, messages[1:]):
        if previous.role == current.role:
            raise HTTPException(status_code=422, detail="Conversation roles must alternate")
    if require_user_turn and messages[-1].role != "user":
        raise HTTPException(status_code=422, detail="A user message is required")

_scenarios_cache: list | None = None
_scenarios_mtime: float = 0.0

def load_scenarios():
    """시나리오 로드. 파일 변경 시 자동으로 캐시 무효화."""
    global _scenarios_cache, _scenarios_mtime
    if not os.path.exists(DATA_PATH):
        return []
    current_mtime = os.path.getmtime(DATA_PATH)
    if _scenarios_cache is not None and current_mtime == _scenarios_mtime:
        return _scenarios_cache
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        _scenarios_cache = json.load(f)
    _scenarios_mtime = current_mtime
    return _scenarios_cache

async def _llm_chat(request: Request, messages: list, system_prompt: str, temperature: float = 0.7) -> str:
    """멀티턴 대화 LLM 호출 — 백엔드 분기 + 폴백을 한 곳에서 처리."""
    primary = request.app.state.model_backend
    fallback = getattr(request.app.state, "model_backend_fallback", "")
    backends = [primary] if primary else ["ollama"]
    if fallback and fallback != primary:
        backends.append(fallback)

    for backend in backends:
        try:
            if backend == "gemini":
                from google.genai import types as genai_types
                contents = [
                    genai_types.Content(
                        role="user" if m["role"] == "user" else "model",
                        parts=[genai_types.Part(text=m["content"])]
                    )
                    for m in messages
                ]
                config = genai_types.GenerateContentConfig(system_instruction=system_prompt, temperature=temperature)
                resp = await asyncio.to_thread(
                    request.app.state.gemini_client.models.generate_content,
                    model=request.app.state.gemini_model, contents=contents, config=config,
                )
                out = resp.text or ""
                if out: return out
            elif backend == "openai":
                resp = await asyncio.to_thread(
                    request.app.state.openai_client.chat.completions.create,
                    model=request.app.state.openai_model,
                    messages=[{"role": "system", "content": system_prompt}] + messages,
                    temperature=temperature,
                )
                out = resp.choices[0].message.content or ""
                if out: return out
            elif backend == "ollama":
                prompt = system_prompt + "\n\n대화 기록:\n" + "\n".join(
                    f"{m['role']}: {m['content']}" for m in messages
                )
                resp = await asyncio.to_thread(
                    requests.post,
                    f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/generate",
                    json={"model": os.getenv("OLLAMA_MODEL", "exaone3.5:7.8b"), "prompt": prompt,
                          "stream": False, "options": {"temperature": temperature}},
                    timeout=60,
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"Ollama 응답 오류 {resp.status_code}: {resp.text}")
                out = resp.json().get("response", "")
                if out: return out
        except Exception:
            if backend == backends[-1]:
                raise
            continue  # try fallback
    raise RuntimeError("All LLM backends failed")


async def _llm_complete(request: Request, prompt: str, temperature: float = 0.7) -> str:
    """단일 프롬프트 LLM 호출 — 평가 등 단일턴 용도 + 폴백."""
    primary = request.app.state.model_backend
    fallback = getattr(request.app.state, "model_backend_fallback", "")
    backends = [primary] if primary else ["ollama"]
    if fallback and fallback != primary:
        backends.append(fallback)

    for backend in backends:
        try:
            if backend == "gemini":
                resp = await asyncio.to_thread(
                    request.app.state.gemini_client.models.generate_content,
                    model=request.app.state.gemini_model, contents=prompt,
                )
                out = resp.text or ""
                if out: return out
            elif backend == "openai":
                resp = await asyncio.to_thread(
                    request.app.state.openai_client.chat.completions.create,
                    model=request.app.state.openai_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                )
                out = resp.choices[0].message.content or ""
                if out: return out
            elif backend == "ollama":
                resp = await asyncio.to_thread(
                    requests.post,
                    f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/generate",
                    json={"model": os.getenv("OLLAMA_MODEL", "exaone3.5:2.4b"), "prompt": prompt,
                          "stream": False, "options": {"temperature": temperature}},
                    timeout=60,
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"Ollama 응답 오류 {resp.status_code}: {resp.text}")
                out = resp.json().get("response", "")
                if out: return out
        except Exception:
            if backend == backends[-1]:
                raise
            continue  # try fallback
    raise RuntimeError("All LLM backends failed")


def _parse_chat_response(raw: str) -> tuple[str, list]:
    """JSON 형식 LLM 응답에서 (message, vocab) 추출. 파싱 실패 시 raw 전체를 message로."""
    candidates = [raw.strip()]
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
    if fence:
        candidates.insert(0, fence.group(1).strip())
    brace = re.search(r"(\{[\s\S]*\})", raw)
    if brace:
        candidates.append(brace.group(1))
    for text in candidates:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "message" in parsed:
                return str(parsed["message"]), list(parsed.get("vocab") or [])
        except Exception:
            pass
    return raw.strip(), []


def _custom_row_to_scenario(row) -> dict:
    scenario = dict(row)
    for field in ("topics", "goals", "keywords"):
        try:
            scenario[field] = json.loads(scenario.pop(f"{field}_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            scenario[field] = []
    scenario["is_custom"] = True
    return scenario


def _load_custom_scenarios(db_path: str, user_id: int) -> list[dict]:
    with connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM user_roleplay_scenarios WHERE user_id=? ORDER BY sort_order ASC, updated_at DESC, title COLLATE NOCASE",
            (user_id,),
        ).fetchall()
        return [_custom_row_to_scenario(row) for row in rows]


def _load_scenarios_for_user(db_path: str, user_id: int) -> list[dict]:
    return load_scenarios() + _load_custom_scenarios(db_path, user_id)


def _get_owned_custom_scenario(db_path: str, scenario_id: str, user_id: int):
    with connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM user_roleplay_scenarios WHERE id=? AND user_id=?",
            (scenario_id, user_id),
        ).fetchone()
        return _custom_row_to_scenario(row) if row else None


def _scenario_for_user(db_path: str, scenario_id: str, user_id: int) -> dict | None:
    scenario = next((s for s in load_scenarios() if s["id"] == scenario_id), None)
    return scenario or _get_owned_custom_scenario(db_path, scenario_id, user_id)


def _scenario_values(payload: CustomScenarioRequest) -> tuple:
    return (
        payload.title.strip(), payload.description.strip(), payload.level.strip(),
        payload.initial_message.strip(), payload.persona.strip(), payload.era.strip(),
        payload.speaking_style.strip(), json.dumps(payload.topics, ensure_ascii=False),
        json.dumps(payload.goals, ensure_ascii=False), json.dumps(payload.keywords, ensure_ascii=False),
        payload.tts_voice.strip() or "Kore", payload.image.strip() if payload.image else None,
    )


@router.get("/roleplay", response_class=HTMLResponse)
async def roleplay_page(request: Request):
    if redir := getattr(request.app.state, "redirect_if_unauthenticated", lambda r: None)(request):
        return redir
    return request.app.state.templates.TemplateResponse(request, "ai-roleplay.html")

@router.get("/api/roleplay/scenarios")
async def get_scenarios(request: Request, user: dict = Depends(get_current_user)):
    return _load_scenarios_for_user(request.app.state.db_path, user["id"])


@router.post("/api/roleplay/scenarios/custom")
async def create_custom_scenario(
    request: Request, payload: CustomScenarioRequest, user: dict = Depends(get_current_user)
):
    scenario_id = f"custom-{uuid4().hex}"
    values = _scenario_values(payload)
    with connect(request.app.state.db_path) as conn:
        next_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM user_roleplay_scenarios WHERE user_id=?",
            (user["id"],),
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO user_roleplay_scenarios
            (id, user_id, title, description, level, initial_message, persona, era,
             speaking_style, topics_json, goals_json, keywords_json, tts_voice, image, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (scenario_id, user["id"], *values, next_order),
        )
        conn.commit()
    return _get_owned_custom_scenario(request.app.state.db_path, scenario_id, user["id"])


@router.put("/api/roleplay/scenarios/custom/{scenario_id}")
async def update_custom_scenario(
    scenario_id: str, request: Request, payload: CustomScenarioUpdate, user: dict = Depends(get_current_user)
):
    if not scenario_id.startswith("custom-"):
        raise HTTPException(status_code=400, detail="Only custom scenarios can be edited")
    if not _get_owned_custom_scenario(request.app.state.db_path, scenario_id, user["id"]):
        raise HTTPException(status_code=404, detail="Scenario not found")
    values = _scenario_values(payload)
    with connect(request.app.state.db_path) as conn:
        conn.execute(
            """UPDATE user_roleplay_scenarios
            SET title=?, description=?, level=?, initial_message=?, persona=?, era=?,
                speaking_style=?, topics_json=?, goals_json=?, keywords_json=?, tts_voice=?, image=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND user_id=?""",
            (*values, scenario_id, user["id"]),
        )
        conn.commit()
    return _get_owned_custom_scenario(request.app.state.db_path, scenario_id, user["id"])


@router.post("/api/roleplay/scenarios/custom/reorder")
async def reorder_custom_scenarios(
    request: Request, payload: CustomScenarioReorderRequest, user: dict = Depends(get_current_user)
):
    scenario_ids = payload.scenario_ids
    if len(scenario_ids) != len(set(scenario_ids)) or any(not item.startswith("custom-") for item in scenario_ids):
        raise HTTPException(status_code=422, detail="Invalid custom scenario order")
    with connect(request.app.state.db_path) as conn:
        rows = conn.execute(
            "SELECT id FROM user_roleplay_scenarios WHERE user_id=?", (user["id"],)
        ).fetchall()
        owned_ids = {row[0] for row in rows}
        if set(scenario_ids) != owned_ids:
            raise HTTPException(status_code=422, detail="Scenario order must include all owned scenarios")
        conn.executemany(
            "UPDATE user_roleplay_scenarios SET sort_order=? WHERE id=? AND user_id=?",
            [(index, scenario_id, user["id"]) for index, scenario_id in enumerate(scenario_ids)],
        )
        conn.commit()
    return {"status": "success"}


@router.delete("/api/roleplay/scenarios/custom/{scenario_id}")
async def delete_custom_scenario(
    scenario_id: str, request: Request, user: dict = Depends(get_current_user)
):
    if not scenario_id.startswith("custom-"):
        raise HTTPException(status_code=400, detail="Only custom scenarios can be deleted")
    with connect(request.app.state.db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM user_roleplay_scenarios WHERE id=? AND user_id=?",
            (scenario_id, user["id"]),
        )
        conn.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {"status": "success"}

@router.post("/api/roleplay/chat")
async def roleplay_chat(request: Request, payload: ChatRequest, user: dict = Depends(get_current_user)):
    db_path = request.app.state.db_path
    scenario = _scenario_for_user(db_path, payload.scenario_id, user["id"])

    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    _validate_history(payload.messages, require_user_turn=True)
    messages = [message.model_dump() for message in payload.messages]

    credit_costs = request.app.state.credit_costs
    daily_credits = int(os.getenv("DAILY_CREDITS", "100"))
    credit = check_and_consume_credits(db_path, user["id"], credit_costs.get("chat", 2), daily_credits)
    if not credit["ok"]:
        return JSONResponse(status_code=429, content={
            "error": f"오늘의 크레딧이 부족합니다. 자정에 리셋됩니다. (남은 크레딧: {credit['remaining']})"
        })

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
5. 학습자가 문법이나 표현을 틀리면 캐릭터를 유지하며 한 문장 이내로 부드럽게 교정해 주세요.
6. 반드시 다음 JSON 형식으로만 출력하세요 (코드 펜스 없이 순수 JSON):
{{"message": "3~5문장 한국어 대화", "vocab": [{{"word": "핵심 단어/표현", "meaning": "English meaning"}}, ...]}}
vocab에는 이 답변의 핵심 어휘/표현 2~3개만 포함하세요."""

    try:
        raw = await _llm_chat(request, messages, system_prompt)
        message, vocab = _parse_chat_response(raw)
        romanized = romanize_korean(message)
        return {"message": message, "romanized": romanized, "vocab": vocab}
    except Exception as e:
        refund_consumed_credits(
            db_path, user["id"], credit_costs.get("chat", 2), daily_credits
        )
        logger.error(f"Roleplay chat error: {e}")
        return JSONResponse(status_code=500, content={"error": "AI 응답을 처리하지 못했습니다."})

@router.post("/api/roleplay/evaluate")
async def roleplay_evaluate(request: Request, payload: ChatRequest, user: dict = Depends(get_current_user)):
    db_path = request.app.state.db_path
    scenario = _scenario_for_user(db_path, payload.scenario_id, user["id"])

    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    # 전체 대화 내용을 바탕으로 평가 프롬프트 구성
    _validate_history(payload.messages)
    messages = [message.model_dump() for message in payload.messages]
    chat_log = "\n".join([f"{m['role']}: {m['content']}" for m in messages])

    title = scenario.get("title", "")
    eval_goals = scenario.get("goals") or []
    keywords = scenario.get("keywords") or []

    credit_costs = request.app.state.credit_costs
    daily_credits = int(os.getenv("DAILY_CREDITS", "100"))
    credit = check_and_consume_credits(db_path, user["id"], credit_costs.get("lesson", 3), daily_credits)
    if not credit["ok"]:
        return JSONResponse(status_code=429, content={
            "error": f"오늘의 크레딧이 부족합니다. 자정에 리셋됩니다. (남은 크레딧: {credit['remaining']})"
        })

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

    try:
        raw_output = await _llm_complete(request, eval_prompt, temperature=0.5)

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
        refund_consumed_credits(
            db_path, user["id"], credit_costs.get("lesson", 3), daily_credits
        )
        logger.error(f"Roleplay evaluate error: {e}")
        return JSONResponse(status_code=500, content={"error": "평가 결과를 생성하지 못했습니다."})
