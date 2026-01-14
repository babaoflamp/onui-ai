from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


router = APIRouter()


@router.get("/sentence-learning")
def sentence_learning_general_page(request: Request):
    """일반 한국어 문장 학습 페이지 (진도 저장/재개)"""
    templates = getattr(request.app.state, "templates", None)
    if templates is None:
        return JSONResponse(status_code=500, content={"error": "Templates not configured"})
    return templates.TemplateResponse(
        "sentence-learning-general.html",
        {"request": request},
    )


@router.get("/api/sentence-learning/state/{user_id}")
async def get_sentence_learning_state(request: Request, user_id: str, scope: str = "all"):
    """문장 학습(일반) 마지막 상태 조회"""
    try:
        learning_service = getattr(request.app.state, "learning_service", None)
        if learning_service is None:
            return JSONResponse(status_code=500, content={"error": "Learning service not configured"})

        state = learning_service.get_or_create_sentence_learning_state(user_id, scope=scope)
        return JSONResponse(state)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/sentence-learning/state")
async def update_sentence_learning_state(request: Request):
    """문장 학습(일반) 마지막 상태 저장"""
    try:
        data = await request.json()
        user_id = data.get("user_id", "anonymous")
        scope = data.get("scope", "all")
        current_sentence_id = data.get("current_sentence_id")
        current_index = data.get("current_index", 0)
        completed_sentence_ids = data.get("completed_sentence_ids", [])

        learning_service = getattr(request.app.state, "learning_service", None)
        if learning_service is None:
            return JSONResponse(status_code=500, content={"error": "Learning service not configured", "success": False})

        state = learning_service.update_sentence_learning_state(
            user_id=user_id,
            scope=scope,
            current_sentence_id=current_sentence_id,
            current_index=current_index,
            completed_sentence_ids=completed_sentence_ids,
        )
        return JSONResponse({"success": True, "state": state})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "success": False})
