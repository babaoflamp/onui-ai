"""
DALL-E 이미지 생성 서비스
OpenAI DALL-E 3 API를 사용한 이미지 생성 및 로컬 저장
"""

import os
import logging
import asyncio
import aiohttp
import aiofiles
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# OpenAI 설정
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DALLE_MODEL = os.getenv("DALLE_MODEL", "dall-e-3")
DALLE_SIZE = os.getenv("DALLE_IMAGE_SIZE", "1024x1024")
DALLE_QUALITY = os.getenv("DALLE_QUALITY", "standard")
DALLE_STYLE = os.getenv("DALLE_STYLE", "vivid")
DALLE_TIMEOUT = int(os.getenv("DALLE_TIMEOUT", "60"))
DALLE_RETRY_ATTEMPTS = int(os.getenv("DALLE_RETRY_ATTEMPTS", "3"))

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

            # DALL-E API 호출 (동기 함수를 비동기로 실행)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.images.generate(
                    model=DALLE_MODEL,
                    prompt=prompt,
                    size=size,
                    quality=quality,
                    style=style,
                    n=1
                )
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
        "illustration": "illustration style, clean and educational",
        "realistic": "photorealistic style, professional photography",
        "painting": "oil painting style, artistic",
        "sketch": "detailed pencil sketch, line art",
        "cartoon": "cartoon style, cheerful and colorful",
        "watercolor": "watercolor painting style"
    }

    style_desc = style_descriptions.get(style, "illustration style")

    # 한국 학습 컨텍스트 추가
    enhanced_prompt = f"{korean_situation}, {style_desc}, "
    enhanced_prompt += "bright and clear, suitable for language learning materials, "
    enhanced_prompt += "Korean cultural context, educational purpose"

    logger.info(f"Enhanced prompt: {enhanced_prompt}")

    return enhanced_prompt


async def translate_korean_to_english_prompt(korean_text: str) -> str:
    """
    한국어 텍스트를 DALL-E용 영어 프롬프트로 번역
    (현재는 단순히 한국어를 그대로 사용하지만, 추후 번역 API 연동 가능)

    Args:
        korean_text: 한국어 텍스트

    Returns:
        영어 프롬프트 (현재는 한국어 그대로 반환)
    """
    # TODO: 실제 번역 API 연동 시 구현
    # 현재는 DALL-E가 한국어도 어느 정도 이해하므로 그대로 전달
    return korean_text
