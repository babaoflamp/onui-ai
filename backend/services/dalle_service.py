"""
DALL-E 이미지 생성 서비스
OpenAI DALL-E 3 API를 사용한 이미지 생성 및 로컬 저장
"""

import os
import logging
import asyncio
import aiohttp
import aiofiles
import requests
import base64
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

try:
    import google.generativeai as genai
except Exception:
    genai = None

# .env 파일 로드
load_dotenv()

logger = logging.getLogger(__name__)

# OpenAI 설정
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DALLE_MODEL = os.getenv("DALLE_MODEL", "gpt-image-1.5")
DALLE_SIZE = os.getenv("DALLE_IMAGE_SIZE", "1024x1024")
DALLE_QUALITY = os.getenv("DALLE_QUALITY", "standard")
DALLE_STYLE = os.getenv("DALLE_STYLE", "vivid")
DALLE_TIMEOUT = int(os.getenv("DALLE_TIMEOUT", "60"))
DALLE_RETRY_ATTEMPTS = int(os.getenv("DALLE_RETRY_ATTEMPTS", "3"))

# Gemini 설정 (옵션)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv(
    "GEMINI_IMAGE_MODEL",
    os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
)

# 이미지 저장 디렉토리
UPLOAD_DIR = Path("uploads/images")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def download_and_save_image(image_url: str, filename: str) -> str:
    """
    URL에서 이미지를 다운로드하여 로컬에 저장

    Args:
        image_url: 다운로드할 이미지 URL
        filename: 저장할 파일명

    Returns:
        저장된 로컬 파일 경로
    """
    try:
        filepath = UPLOAD_DIR / filename

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    content = await response.read()
                    async with aiofiles.open(filepath, 'wb') as f:
                        await f.write(content)

                    logger.info(f"Image saved to {filepath}")
                    return f"/uploads/images/{filename}"
                else:
                    raise Exception(f"Failed to download image: HTTP {response.status}")

    except Exception as e:
        logger.error(f"Error downloading image: {e}")
        raise


async def generate_image_dall_e(
    prompt: str,
    size: str = None,
    quality: str = None,
    style: str = None,
    save_locally: bool = True
) -> Dict[str, Any]:
    """
    OpenAI DALL-E 3 API를 사용하여 이미지 생성

    Args:
        prompt: 이미지 생성 프롬프트 (영어)
        size: 이미지 크기 (1024x1024, 1024x1792, 1792x1024)
        quality: 이미지 품질 (standard, hd)
        style: 이미지 스타일 (vivid, natural)
        save_locally: 로컬에 저장할지 여부

    Returns:
        {
            "success": bool,
            "image_url": str,           # OpenAI URL 또는 로컬 경로
            "local_path": str,          # 로컬 저장 경로 (save_locally=True인 경우)
            "revised_prompt": str,      # DALL-E가 수정한 프롬프트
            "created": int,             # 생성 타임스탬프
            "error": str                # 에러 메시지 (실패 시)
        }
    """
    if not OPENAI_API_KEY:
        return {
            "success": False,
            "error": "OPENAI_API_KEY not configured in environment variables"
        }

    # OpenAI 라이브러리 동적 import
    try:
        from openai import OpenAI
    except ImportError:
        return {
            "success": False,
            "error": "OpenAI library not installed. Run: pip install openai"
        }

    client = OpenAI(api_key=OPENAI_API_KEY)

    size = size or DALLE_SIZE
    quality = quality or DALLE_QUALITY
    style = style or DALLE_STYLE

    # Retry 로직
    for attempt in range(DALLE_RETRY_ATTEMPTS):
        try:
            logger.info(f"Generating image (attempt {attempt + 1}/{DALLE_RETRY_ATTEMPTS})...")
            logger.info(f"Prompt: {prompt[:100]}...")
            logger.info(f"Settings: model={DALLE_MODEL}, size={size}, quality={quality}, style={style}")

            # DALL-E / GPT image API 호출 (동기 함수를 비동기로 실행)
            loop = asyncio.get_event_loop()
            use_quality = quality
            if str(DALLE_MODEL).startswith("gpt-image-"):
                # gpt-image-* supports low/medium/high/auto
                if quality == "hd":
                    use_quality = "high"
                elif quality == "standard":
                    use_quality = "medium"
            kwargs = {
                "model": DALLE_MODEL,
                "prompt": prompt,
                "size": size,
                "quality": use_quality,
                "n": 1,
            }
            if not str(DALLE_MODEL).startswith("gpt-image-"):
                kwargs["style"] = style
            response = await loop.run_in_executor(
                None,
                lambda: client.images.generate(**kwargs)
            )

            image_url = response.data[0].url
            revised_prompt = getattr(response.data[0], 'revised_prompt', prompt)
            created = response.created

            logger.info(f"Image generated successfully: {image_url}")

            result = {
                "success": True,
                "image_url": image_url,
                "revised_prompt": revised_prompt,
                "created": created
            }

            # 로컬 저장
            if save_locally:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"dalle_{timestamp}.png"

                try:
                    local_path = await download_and_save_image(image_url, filename)
                    result["local_path"] = local_path
                    result["image_url"] = local_path  # 로컬 경로로 덮어쓰기
                    logger.info(f"Image saved locally: {local_path}")
                except Exception as download_error:
                    logger.warning(f"Failed to save locally, using OpenAI URL: {download_error}")
                    # 로컬 저장 실패해도 OpenAI URL은 반환

            return result

        except Exception as e:
            logger.error(f"DALL-E error (attempt {attempt + 1}/{DALLE_RETRY_ATTEMPTS}): {e}")

            if attempt == DALLE_RETRY_ATTEMPTS - 1:
                # 마지막 재시도 실패
                return {
                    "success": False,
                    "error": f"Image generation failed after {DALLE_RETRY_ATTEMPTS} attempts: {str(e)}"
                }

            # 지수 백오프
            await asyncio.sleep(2 ** attempt)

    return {
        "success": False,
        "error": "Unknown error occurred"
    }


def _extract_gemini_image_base64(resp):
    """Return (base64, mime_type) if Gemini response contains inline image data."""
    if not resp:
        return None, None

    candidates = getattr(resp, "candidates", None)
    if candidates is None:
        result = getattr(resp, "_result", None)
        candidates = getattr(result, "candidates", None) if result else None

    if not candidates:
        return None, None

    for cand in candidates:
        content = getattr(cand, "content", None)
        parts = None
        if isinstance(content, dict):
            parts = content.get("parts")
        else:
            parts = getattr(content, "parts", None)
        if not parts:
            continue
        for part in parts:
            inline_data = None
            if isinstance(part, dict):
                inline_data = part.get("inline_data")
            else:
                inline_data = getattr(part, "inline_data", None)
            if not inline_data:
                continue
            mime_type = inline_data.get("mime_type") if isinstance(inline_data, dict) else getattr(inline_data, "mime_type", None)
            data = inline_data.get("data") if isinstance(inline_data, dict) else getattr(inline_data, "data", None)
            if not data:
                continue
            if isinstance(data, bytes):
                data = base64.b64encode(data).decode("utf-8")
            return data, (mime_type or "image/png")

    return None, None


def _extract_inline_image_from_dict(data: Dict[str, Any]):
    candidates = data.get("candidates") or []
    for cand in candidates:
        content = cand.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data") or {}
            mime_type = inline.get("mime_type") or inline.get("mimeType") or "image/png"
            img_data = inline.get("data")
            if img_data:
                return img_data, mime_type
    return None, None


def _generate_image_gemini_rest(prompt: str, model_name: str):
    """Gemini REST API image generation (no SDK)."""
    if not GEMINI_API_KEY:
        return {"success": False, "error": "GEMINI_API_KEY not configured"}
    if not model_name:
        return {"success": False, "error": "Gemini model is not configured"}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
    }
    try:
        resp = requests.post(
            url,
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=60,
        )
        if resp.status_code != 200:
            return {"success": False, "error": f"Gemini REST error: {resp.status_code} {resp.text[:200]}"}
        data = resp.json()
        image_base64, mime_type = _extract_inline_image_from_dict(data)
        if not image_base64:
            return {"success": False, "error": "Gemini REST did not return inline image data"}
        return {
            "success": True,
            "image_base64": image_base64,
            "mime_type": mime_type or "image/png",
            "model": model_name,
        }
    except Exception as e:
        return {"success": False, "error": f"Gemini REST failed: {e}"}


async def generate_image_gemini(prompt: str, save_locally: bool = True) -> Dict[str, Any]:
    """Google Gemini 이미지 생성 (시범용 간단 래퍼)."""
    if not GEMINI_API_KEY:
        return {"success": False, "error": "GEMINI_API_KEY not configured"}
    # SDK is optional; REST will be used if unavailable or incompatible.
    sdk_available = bool(genai and hasattr(genai, "GenerativeModel"))

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        models_to_try = [GEMINI_MODEL, "gemini-2.0-flash-exp"]
        seen = set()
        last_error = None

        for model_name in models_to_try:
            if not model_name or model_name in seen:
                continue
            seen.add(model_name)
            try:
                # Prefer SDK first; REST remains as fallback.
                if sdk_available:
                    model = genai.GenerativeModel(model_name)
                    resp = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: model.generate_content(prompt),
                    )

                    image_base64, mime_type = _extract_gemini_image_base64(resp)
                    if not image_base64:
                        last_error = "Gemini SDK did not return inline image data"
                    else:
                        result = {
                            "success": True,
                            "image_base64": image_base64,
                            "mime_type": mime_type or "image/png",
                            "model": model_name,
                        }
                        if save_locally:
                            try:
                                binary = base64.b64decode(image_base64)
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                filename = f"gemini_{timestamp}.png"
                                filepath = UPLOAD_DIR / filename
                                async with aiofiles.open(filepath, "wb") as f:
                                    await f.write(binary)
                                result["local_path"] = f"/uploads/images/{filename}"
                            except Exception as e:
                                logger.warning(f"Failed to save Gemini image locally: {e}")
                        return result

                rest_result = _generate_image_gemini_rest(prompt, model_name)
                if rest_result.get("success"):
                    result = rest_result
                    image_base64 = result.get("image_base64")
                    mime_type = result.get("mime_type")
                else:
                    last_error = rest_result.get("error") or "Gemini REST failed"
                    continue

                if save_locally:
                    try:
                        binary = base64.b64decode(image_base64)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"gemini_{timestamp}.png"
                        filepath = UPLOAD_DIR / filename
                        async with aiofiles.open(filepath, "wb") as f:
                            await f.write(binary)
                        result["local_path"] = f"/uploads/images/{filename}"
                    except Exception as e:
                        logger.warning(f"Failed to save Gemini image locally: {e}")

                return result
            except Exception as e:
                last_error = str(e)
                continue

        return {"success": False, "error": f"Gemini image generation failed: {last_error or 'Unknown error'}"}

    except Exception as e:
        return {"success": False, "error": f"Gemini image generation failed: {e}"}


def enhance_prompt_for_korean_learning(
    korean_situation: str,
    style: str = "illustration"
) -> str:
    """
    한국어 학습용 이미지 프롬프트 최적화
    한국어 상황 설명을 DALL-E에 최적화된 영어 프롬프트로 변환

    Args:
        korean_situation: 한국어로 작성된 상황 설명
        style: 이미지 스타일 (illustration, realistic, painting, sketch)

    Returns:
        최적화된 영어 프롬프트

    Example:
        Input: "서울의 전통 시장에서 과일을 사는 상황"
        Output: "A vibrant traditional Korean market scene in Seoul with fruit vendors..."
    """
    # 스타일 매핑
    style_descriptions = {
        "watercolor": "watercolor painting style, soft and flowing",
        "illustration": "illustration style, clean and educational",
        "cartoon": "cartoon style, cheerful and colorful",
        "realistic": "photorealistic style, professional photography",
        "oil-painting": "oil painting style, rich textures and brushstrokes",
        "pencil-sketch": "detailed pencil sketch, line art, grayscale",
        "digital-art": "digital art style, modern and vibrant",
        "anime": "anime style, Japanese animation aesthetic",
        "vintage": "vintage style, retro colors and aged look",
        "minimalist": "minimalist style, simple and clean composition",
        "pop-art": "pop art style, bold colors and graphic elements",
        "3d-render": "3D rendered style, polished and dimensional"
    }

    style_desc = style_descriptions.get(style, "watercolor painting style")

    # 한국 학습 컨텍스트 추가
    enhanced_prompt = f"{korean_situation}, {style_desc}, "
    enhanced_prompt += "bright and clear, suitable for language learning materials, "
    enhanced_prompt += "Korean cultural context, educational purpose, "
    enhanced_prompt += "no text, no letters, no words, no writing, no signs with text"

    logger.info(f"Enhanced prompt: {enhanced_prompt}")

    return enhanced_prompt


async def translate_korean_to_english_prompt(korean_text: str) -> str:
    """
    한국어 텍스트를 DALL-E용 영어 프롬프트로 번역
    OpenAI GPT-4o-mini를 사용하여 번역 수행

    Args:
        korean_text: 한국어 텍스트

    Returns:
        영어 프롬프트
    """
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set, skipping translation.")
        return korean_text

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # GPT-4o-mini 모델 사용 (기본값 설정이 없으면 하드코딩)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that translates Korean text into descriptive English prompts suitable for DALL-E image generation. Focus on visual details. Output only the translated English text."},
                    {"role": "user", "content": korean_text}
                ],
                temperature=0.7,
                max_tokens=200
            )
        )
        
        english_prompt = response.choices[0].message.content.strip()
        logger.info(f"Translated prompt: '{korean_text}' -> '{english_prompt}'")
        return english_prompt

    except Exception as e:
        logger.error(f"Translation failed: {e}")
        return korean_text
