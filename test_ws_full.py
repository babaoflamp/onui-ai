import asyncio
import websockets
import json
import sys

async def test_full_cycle():
    scenario_id = "starbucks"
    url = f"ws://localhost:9002/ws/voice-call/{scenario_id}"
    print(f"Connecting to {url}...")
    try:
        async with websockets.connect(url) as websocket:
            print("Connected.")
            # 1. Wait for "connected" status
            msg = await websocket.recv()
            print(f"Status: {msg}")
            
            # 2. Wait for initial audio
            audio_received = False
            transcript_received = False
            
            for _ in range(20):
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                except asyncio.TimeoutError:
                    print("Timeout waiting for response")
                    break
                    
                if isinstance(msg, bytes):
                    # print(f"Received audio ({len(msg)} bytes)")
                    audio_received = True
                else:
                    print(f"Received JSON: {msg}")
                    data = json.loads(msg)
                    if data.get("type") == "ai_transcript_final":
                        transcript_received = True
                    if data.get("type") == "status" and data.get("text") == "connected":
                        continue
                
                if audio_received and transcript_received:
                    break
            
            if audio_received and transcript_received:
                print("✅ Initial greeting received (Audio + Transcript)")
                
                # 3. Send "end_call" message to test JSON control
                print("Sending end_call signal...")
                await websocket.send(json.dumps({"type": "end_call"}))
                
                # 4. Wait for closing
                concluded = False
                for _ in range(20):
                    try:
                        msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        if isinstance(msg, str):
                            data = json.loads(msg)
                            print(f"Received JSON type: {data.get('type')}")
                            if data.get("type") == "call_concluded_by_ai":
                                concluded = True
                                break
                    except asyncio.TimeoutError:
                        break
                
                if concluded:
                    print("✅ AI concluded the call as requested.")
                    print("✅ Full cycle test passed!")
                    sys.exit(0)
                else:
                    print("❌ AI did not conclude the call in time.")
                    sys.exit(1)
            else:
                print(f"❌ Failed to receive initial greeting. Audio: {audio_received}, Transcript: {transcript_received}")
                sys.exit(1)
                
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_full_cycle())
