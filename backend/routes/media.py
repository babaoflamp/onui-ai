import os
import json
import logging
import sqlite3
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, Depends, Form
from fastapi.responses import JSONResponse

from backend.routes.deps import get_current_user, load_json_data

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

@router.get("/api/tube/videos")
async def get_tube_videos(user: dict = Depends(get_current_user)):
    videos = load_json_data("onui-tube.json") or []
    return {"success": True, "videos": videos}

@router.post("/api/tube/videos")
async def update_tube_videos(request: Request, user: dict = Depends(get_current_user)):
    # Admin check might be needed here, but for now matching previous logic
    try:
        data = await request.json()
        with open("data/onui-tube.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"success": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/api/tube/transcripts/{video_id}")
async def get_tube_transcript(video_id: str, user: dict = Depends(get_current_user)):
    transcripts = load_json_data("onui-tube-transcripts.json") or {}
    transcript = transcripts.get(video_id)
    if not transcript:
        return JSONResponse(status_code=404, content={"error": "Transcript not found"})
    return {"success": True, "transcript": transcript}

@router.get("/api/tube/vocab/export")
async def export_tube_vocab(user: dict = Depends(get_current_user)):
    vocab = load_json_data("vocabulary.json") or []
    return {"success": True, "vocabulary": vocab}

@router.get("/api/tube/vocab")
async def get_user_tube_vocab(request: Request, user: dict = Depends(get_current_user)):
    db_path = request.app.state.db_path
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT label, pos, meaning, source, saved_at
            FROM user_saved_vocab
            WHERE user_id = ?
            ORDER BY saved_at DESC, id DESC
            """,
            (user["id"],),
        )
        vocab = [
            {
                "label": row["label"],
                "pos": row["pos"] or "",
                "meaning": row["meaning"] or "",
                "mean": row["meaning"] or "",
                "source": row["source"] or "tube",
                "savedAt": row["saved_at"],
            }
            for row in cursor.fetchall()
        ]
        return {"success": True, "vocab": vocab}
    finally:
        conn.close()

@router.post("/api/tube/vocab")
async def update_user_tube_vocab(request: Request, user: dict = Depends(get_current_user)):
    db_path = request.app.state.db_path
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        content_type = (request.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            data = await request.json()
            vocab = data.get("vocabulary", [])
            if not isinstance(vocab, list):
                raise HTTPException(status_code=400, detail="Invalid vocabulary payload")

            cursor.execute("DELETE FROM user_saved_vocab WHERE user_id = ?", (user["id"],))
            for item in vocab:
                if isinstance(item, str):
                    label = item.strip()
                    pos = ""
                    meaning = ""
                    source = "tube"
                elif isinstance(item, dict):
                    label = str(item.get("label", "") or "").strip()
                    pos = str(item.get("pos", "") or "").strip()
                    meaning = str(item.get("meaning") or item.get("mean") or "").strip()
                    source = str(item.get("source", "tube") or "tube").strip()
                else:
                    continue

                if not label:
                    continue

                cursor.execute(
                    """
                    INSERT INTO user_saved_vocab (user_id, label, pos, meaning, source)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user["id"], label, pos, meaning, source),
                )
        else:
            form = await request.form()
            label = str(form.get("label", "") or "").strip()
            if not label:
                raise HTTPException(status_code=400, detail="label is required")

            pos = str(form.get("pos", "") or "").strip()
            meaning = str(form.get("meaning", "") or "").strip()
            source = str(form.get("source", "tube") or "tube").strip()

            cursor.execute(
                """
                INSERT INTO user_saved_vocab (user_id, label, pos, meaning, source)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, label) DO UPDATE SET
                    pos = excluded.pos,
                    meaning = excluded.meaning,
                    source = excluded.source,
                    saved_at = CURRENT_TIMESTAMP
                """,
                (user["id"], label, pos, meaning, source),
            )

        conn.commit()
        return {"success": True}
    finally:
        conn.close()
