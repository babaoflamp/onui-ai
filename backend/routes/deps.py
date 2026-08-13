"""
FastAPI Dependencies for Routes
"""
from backend.utils import (
    get_current_user,
    get_current_admin_user,
    get_optional_user,
    get_user_by_id,
    get_session,
    create_session_token,
    parse_session_token,
    hash_password,
    verify_password,
    load_json_data,
    get_user_credits,
    check_and_consume_credits,
    refund_consumed_credits,
    ensure_rag_tables,
    rag_chunk_text,
    rag_get_settings,
    rag_search,
    romanize_korean,
    parse_model_output,
    list_ollama_models,
    ensure_wav_16k_mono,
    transcribe_with_vosk
)
