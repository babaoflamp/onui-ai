#!/usr/bin/env python3
"""
Generate and save high-quality thumbnail images for OnuiTube videos.
Uses the current Gemini image generation model unless GEMINI_IMAGE_MODEL is set.
"""

import os
import sys
import json
import asyncio
import argparse
import requests
import shutil
import base64
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Keep this aligned with the rest of the project, while allowing .env overrides.
os.environ.setdefault("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")

from backend.services.dalle_service import generate_image_gemini

# Load environment variables (will not override GEMINI_IMAGE_MODEL set above if already in environ)
load_dotenv()

TUBE_DATA_PATH = Path("data/onui-tube.json")
OUTPUT_DIR = Path("static/images/tube")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Detailed character and style description for consistency with the original OnuiTube set.
CHARACTER_DESC = (
    "Onui, the same cute young Korean female learning guide from the existing OnuiTube thumbnails: "
    "large expressive brown eyes, bright smile, long black hair in a high ponytail with soft bangs. "
    "Keep her face and hair consistent, but vary her outfit naturally for each scene like the original thumbnails"
)
STYLE_DESC = (
    "Square 1024x1024 polished 3D educational illustration, bright cheerful high-key lighting, "
    "vibrant pastel colors, clean daylight, soft shadows, rounded Pixar-like character design, "
    "detailed real-life Korean learning environment, medium shot, scene-based thumbnail composition "
    "like a bright language textbook cover"
)
AVOID_DESC = (
    "Do not make an infographic, poster card, UI screen, title slide, sticker sheet, mascot lineup, speech bubble, "
    "floating icon layout, or isolated full-body character on a plain background. "
    "Do not repeat the same blue denim jacket and yellow bag outfit across every image. "
    "Avoid dark, moody, cinematic, low-light, or brown-heavy color grading. "
    "No large readable title text, no subtitles, no labels, no English text, no watermark. "
    "Incidental background signage may exist but should not dominate the image."
)

OUTFIT_OVERRIDES = {
    "airport_checkin": "casual travel outfit with a light sky-blue cardigan, white shirt, beige skirt or pants, and a small rolling suitcase; no yellow crossbody bag",
    "asking_directions": "bright yellow vest over a white blouse with a small backpack, travel-friendly but not denim",
    "cafe_ordering": "cream cardigan with an orange scarf and casual slacks, warm cafe-friendly outfit",
    "clothes_shopping": "light blue denim jacket is acceptable only here, paired with a white top and tan skirt, holding clothing on a hanger",
    "convenience_store": "clean white casual jacket over a teal shirt, holding convenience-store items, no crossbody bag",
    "doctor_visit": "soft pink hoodie or cardigan, sitting as a patient in a clinic, no denim jacket",
    "hotel_checkin": "neat travel blazer in coral or mint with a small suitcase, no yellow bag",
    "restaurant_ordering": "yellow striped sweater or light cardigan, seated at a restaurant table, no denim jacket",
    "subway_navigation": "blue-and-white casual jacket or light hoodie with a transit card, no yellow crossbody bag",
    "workplace_greetings": "smart casual office blouse with a light beige blazer, laptop or folder nearby, no denim jacket",
    "weather_small_talk": "light mint cardigan over a white blouse, holding a small umbrella and phone weather app, fresh spring outfit",
    "family_intro_basic": "soft lavender sweater and cream skirt, holding a small framed family photo, warm home-friendly outfit",
    "hobbies_weekend": "casual coral sweatshirt with art apron and rolled sleeves, holding a sketchbook and colored pencils",
    "taxi_destination": "neat travel outfit with a beige trench coat and small shoulder bag, sitting in the back seat of a taxi",
    "phone_number_booking": "polished casual navy cardigan and white shirt, holding a phone and small reservation notebook",
    "pharmacy_basic": "comfortable pale green hoodie with a small scarf, holding medicine packaging at a pharmacy counter",
    "school_schedule": "bright campus outfit with a sky-blue cardigan and backpack, holding a timetable and books",
    "paying_card_cash": "clean cream jacket with teal shirt, holding a credit card and receipt at a checkout counter",
    "photo_request": "travel-friendly pink cardigan and small backpack, holding a phone near a scenic Korean landmark",
    "delivery_order_basic": "cozy yellow sweater at home, holding a phone with delivery order screen and waiting near the door",
    "bank_account": "smart casual mint blazer and white blouse, holding identification documents at a bank desk",
    "post_office_package": "casual orange cardigan and comfortable pants, holding a labeled package at a post office counter",
    "real_estate_viewing": "neat beige blazer and sneakers, holding a clipboard while viewing a bright apartment room",
    "hair_salon": "soft peach blouse with hair clips visible, seated in a salon chair with a cape around shoulders",
    "lost_item_report": "light blue jacket and worried expression, holding a phone and describing a missing bag to station staff",
    "making_appointment": "tidy rose cardigan, holding a calendar app and hospital appointment card",
    "delivery_problem": "casual home outfit in teal hoodie, checking a delivery bag with a concerned but polite expression",
    "job_interview_intro": "professional ivory blazer and navy blouse, seated for an interview with a portfolio folder",
    "public_office_document": "modest gray cardigan and white blouse, holding ID and document request form at a public office",
    "inviting_friend": "warm casual orange sweater, setting a table with snacks for friends at home",
    "apartment_repair_request": "practical light green cardigan, pointing toward a leaking kitchen sink while holding a phone",
    "work_feedback_meeting": "professional beige blazer and burgundy blouse, speaking in a meeting with documents on the table",
    "university_presentation_qna": "academic navy cardigan and white blouse, standing near a presentation screen with notes",
    "news_opinion": "smart casual blue sweater, discussing news while holding a tablet in a cafe",
    "culture_comparison_honorifics": "elegant hanbok-inspired pastel jacket over modern clothes, explaining respectfully with gesture",
    "travel_complaint_refund": "travel outfit with coral jacket and suitcase, politely speaking at a hotel or travel service desk",
    "health_insurance_claim": "calm professional mint blouse, holding medical documents and phone app at an insurance counter",
    "contract_negotiation": "business-style charcoal blazer and cream blouse, reviewing contract papers across a table",
    "neighbor_noise_complaint": "comfortable home cardigan, politely talking in an apartment hallway with a concerned expression",
    "recycling_policy_discussion": "green casual jacket and jeans, holding sorted recycling items near apartment recycling bins",
}

SCENE_OVERRIDES = {
    "airport_checkin": (
        "Onui is at a busy airport check-in counter with a suitcase, passport, boarding pass, airline staff, "
        "queue barriers, luggage scale, and departure-board atmosphere"
    ),
    "asking_directions": (
        "Onui is on a Korean city street asking a friendly local person for directions while holding an unfolded map; "
        "subway entrance, street signs, storefronts, and pedestrians in the background"
    ),
    "cafe_ordering": (
        "Onui is ordering drinks at a cozy Korean cafe counter, speaking with a barista, with espresso machine, "
        "menu board, pastries, cups, and warm cafe lighting"
    ),
    "clothes_shopping": (
        "Onui is shopping in a bright clothing store, comparing shirts on hangers with a shop assistant nearby, "
        "racks of colorful clothes, mirror, and fitting room in the background"
    ),
    "convenience_store": (
        "Onui is at a Korean convenience store checkout holding a lunch box and bottled drink, cashier at register, "
        "snack shelves, microwave area, and refrigerated drinks behind her"
    ),
    "doctor_visit": (
        "Onui is in a clean Korean clinic consultation room speaking with a doctor holding a clipboard, with medical poster, "
        "desk, chair, and examination tools in the background"
    ),
    "hotel_checkin": (
        "Onui is checking in at a hotel reception desk with a small suitcase, hotel clerk handing over a key card, "
        "lobby plants, counter bell, and warm reception lighting"
    ),
    "restaurant_ordering": (
        "Onui is sitting at a Korean restaurant table ordering food from a server, with menu, side dishes, bowls, "
        "other diners, and warm restaurant lighting"
    ),
    "subway_navigation": (
        "Onui is in a Korean subway station looking at a transit map with a helpful station staff member, "
        "ticket gates, platform signs, stairs, and commuters in the background"
    ),
    "workplace_greetings": (
        "Onui is in a modern Korean office greeting coworkers near a meeting table, laptop, presentation screen, "
        "coffee cups, charts, and morning office light"
    ),
    "weather_small_talk": (
        "Onui is chatting with a neighbor on a bright Korean street after checking the weather, with blue sky, "
        "light breeze, trees, umbrellas near a shop entrance, and friendly daily-life atmosphere"
    ),
    "family_intro_basic": (
        "Onui is in a cozy Korean living room introducing family members using a family photo, with sofa, plants, "
        "photo frames, tea table, and warm daylight"
    ),
    "hobbies_weekend": (
        "Onui is enjoying weekend hobbies at a sunny park art table with a friend, sketchbook, colored pencils, "
        "picnic mat, trees, and people walking in the background"
    ),
    "taxi_destination": (
        "Onui is in the back seat of a Korean taxi speaking politely to the driver, with city street, taxi meter, "
        "navigation screen, and station signs visible through the window"
    ),
    "phone_number_booking": (
        "Onui is making a restaurant reservation by phone at a small desk, with calendar, notebook, clock, "
        "and a cozy evening restaurant image on a tablet nearby"
    ),
    "pharmacy_basic": (
        "Onui is at a bright Korean pharmacy counter explaining cold symptoms to a pharmacist, with medicine shelves, "
        "health products, consultation counter, and clean lighting"
    ),
    "school_schedule": (
        "Onui is on a language school campus checking a class schedule with books and backpack, with classroom door, "
        "clock, bulletin board, and students in the background"
    ),
    "paying_card_cash": (
        "Onui is at a clean store checkout choosing between card and cash, with cashier, receipt printer, payment terminal, "
        "shopping basket, and bright retail lighting"
    ),
    "photo_request": (
        "Onui is politely asking a passerby to take her photo near a recognizable Korean city landmark, with phone camera, "
        "tourists, stone path, and sunny travel mood"
    ),
    "delivery_order_basic": (
        "Onui is ordering food delivery from home with a phone, delivery bag near the door, apartment intercom, "
        "Korean food on screen, and cozy evening room lighting"
    ),
    "bank_account": (
        "Onui is at a bank consultation desk opening an account with a bank employee, ID cards, forms, computer monitor, "
        "queue number display, and clean professional bank interior"
    ),
    "post_office_package": (
        "Onui is sending a package at a Korean post office counter with clerk, parcel scale, shipping labels, boxes, "
        "postal posters, and organized queue area"
    ),
    "real_estate_viewing": (
        "Onui is touring a bright Korean studio apartment with a real estate agent, checking sunlight, kitchen, window, "
        "floor plan, and clean empty-room details"
    ),
    "hair_salon": (
        "Onui is in a modern Korean hair salon explaining a haircut style to a stylist, with mirror, salon chair, "
        "hair tools, product shelves, and warm professional lighting"
    ),
    "lost_item_report": (
        "Onui is reporting a lost bag to subway lost-and-found staff, with station service desk, transit map, phone, "
        "small bag reference, and commuters in the background"
    ),
    "making_appointment": (
        "Onui is calling a clinic to change an appointment while looking at a calendar, with hospital card, desk plant, "
        "phone, clock, and clean clinic reception atmosphere"
    ),
    "delivery_problem": (
        "Onui is checking a delivery order at home and politely contacting customer service, with opened food bag, "
        "missing side dish space, phone chat screen, and table setting"
    ),
    "job_interview_intro": (
        "Onui is sitting in a modern office job interview, introducing herself to two interviewers, with resume folder, "
        "glass meeting room, laptop, and professional daylight"
    ),
    "public_office_document": (
        "Onui is requesting a document at a Korean public office counter, with clerk, ticket number machine, forms, "
        "ID card, and clean civic office interior"
    ),
    "inviting_friend": (
        "Onui is inviting a friend for a weekend visit while preparing a small home table with pizza, drinks, calendar, "
        "phone message, and cheerful apartment setting"
    ),
    "apartment_repair_request": (
        "Onui is showing a leaking kitchen sink to a maintenance worker, with water drops, towel, toolbox, apartment kitchen, "
        "and polite problem-solving atmosphere"
    ),
    "work_feedback_meeting": (
        "Onui is in a workplace feedback meeting discussing project schedule with colleagues, shared document, sticky notes, "
        "laptop, meeting table, and constructive professional mood"
    ),
    "university_presentation_qna": (
        "Onui is answering questions after a university presentation, standing near slides and classmates, with podium, "
        "projector screen, lecture room, and academic atmosphere"
    ),
    "news_opinion": (
        "Onui is discussing a news article on a tablet in a cafe with a classmate, with public transportation image on screen, "
        "coffee cups, window light, and thoughtful conversation mood"
    ),
    "culture_comparison_honorifics": (
        "Onui is explaining Korean honorifics to international learners in a cultural classroom, with polite bow gesture, "
        "whiteboard diagrams, Korean tea set, and warm cross-cultural atmosphere"
    ),
    "travel_complaint_refund": (
        "Onui is politely requesting a travel refund at a hotel or travel service desk, with suitcase, booking document, "
        "staff member, room photo on tablet, and calm complaint-handling scene"
    ),
    "health_insurance_claim": (
        "Onui is asking about a health insurance claim at a service counter, with medical receipts, certificate documents, "
        "mobile app screen, consultant, and clean office setting"
    ),
    "contract_negotiation": (
        "Onui is negotiating contract terms across a meeting table, with contract papers, pen, calendar, partner representative, "
        "and focused business conversation atmosphere"
    ),
    "neighbor_noise_complaint": (
        "Onui is politely talking with a neighbor in an apartment hallway about late-night noise, with door, soft hallway lights, "
        "music note hint, and respectful conversation posture"
    ),
    "recycling_policy_discussion": (
        "Onui is discussing apartment recycling rules near clean recycling bins, with sorted plastic, paper, cans, apartment notice board, "
        "resident neighbor, and bright eco-friendly atmosphere"
    ),
}

async def generate_thumbnail(video_id, title, description):
    """Generate and save thumbnail using Gemini"""
    print(f"\n🎬 Processing: {title} ({video_id})")
    
    scene = SCENE_OVERRIDES.get(video_id, description)
    outfit = OUTFIT_OVERRIDES.get(video_id, "scene-appropriate outfit that differs from the other thumbnails")
    prompt = (
        f"{STYLE_DESC}.\n"
        f"Main character: {CHARACTER_DESC}.\n"
        f"Outfit for this scene: {outfit}.\n"
        f"Scene: {scene}.\n"
        f"Composition: Onui should be integrated naturally into the environment with supporting people and props, "
        f"not centered alone; use a lively, detailed, bright scene similar to the original OnuiTube thumbnails. "
        f"Keep the overall exposure bright and colorful, closer to the original 10 images than to a dark cinematic render.\n"
        f"Avoid: {AVOID_DESC}"
    )
    
    print(f"   Prompt: {prompt[:80]}...")
    
    # Try Gemini directly
    print(f"   Generating with Gemini Image ({os.environ['GEMINI_IMAGE_MODEL']})...")
    result = await generate_image_gemini(prompt, save_locally=False)
        
    if result.get("success"):
        dest_path = OUTPUT_DIR / f"{video_id}.png"
        
        # Handle base64 from Gemini
        if result.get("image_base64"):
            img_data = base64.b64decode(result["image_base64"])
            with open(dest_path, "wb") as f:
                f.write(img_data)
            print(f"   ✅ Image saved (from base64): {dest_path}")
            return f"/static/images/tube/{video_id}.png"
            
        # Handle URL from Gemini if provided
        image_url = result.get("image_url")
        if image_url:
            try:
                resp = requests.get(image_url, timeout=30, stream=True)
                if resp.status_code == 200:
                    with open(dest_path, 'wb') as f:
                        shutil.copyfileobj(resp.raw, f)
                    print(f"   ✅ Image saved (downloaded): {dest_path}")
                    return f"/static/images/tube/{video_id}.png"
            except Exception as e:
                print(f"      ❌ Download failed: {e}")
                
    print(f"   ❌ Generation failed: {result.get('error')}")
    return None

def parse_args():
    parser = argparse.ArgumentParser(description="Generate OnuiTube thumbnails.")
    parser.add_argument(
        "--ids",
        nargs="+",
        default=None,
        help="Only generate thumbnails for these video IDs. Defaults to every catalog video.",
    )
    return parser.parse_args()

async def main():
    args = parse_args()
    target_ids = set(args.ids) if args.ids else None

    if not TUBE_DATA_PATH.exists():
        print("❌ tube data not found")
        return

    with open(TUBE_DATA_PATH, "r", encoding="utf-8") as f:
        videos = json.load(f)

    targets = [video for video in videos if target_ids is None or video["id"] in target_ids]
    print(f"🚀 Generating thumbnails for {len(targets)} videos using Gemini {os.environ['GEMINI_IMAGE_MODEL']}...")

    failed = []
    for video in targets:
        new_url = await generate_thumbnail(video["id"], video["title"], video["description"])
        if new_url:
            video["poster_url"] = new_url
            # Save progress
            with open(TUBE_DATA_PATH, "w", encoding="utf-8") as f:
                json.dump(videos, f, ensure_ascii=False, indent=2)
        else:
            failed.append(video["id"])
        
        await asyncio.sleep(1)

    if failed:
        raise SystemExit(f"Thumbnail generation failed for: {', '.join(failed)}")

    print("\n✨ Done!")

if __name__ == "__main__":
    asyncio.run(main())
