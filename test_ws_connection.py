import asyncio
import websockets
import json
import sys

async def test_ws():
    # Use an existing scenario ID from data/voice-call.json
    scenario_id = "subway_staff" 
    url = f"ws://localhost:9002/ws/voice-call/{scenario_id}"
    print(f"Connecting to {url}...")
    try:
        async with websockets.connect(url) as websocket:
            print("Connected to WebSocket server.")
            # The server should send {"type": "status", "text": "connected"}
            # and then maybe an initial audio chunk or another status
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    if isinstance(msg, str):
                        print(f"Received JSON: {msg}")
                        data = json.loads(msg)
                        if data.get("type") == "status" and data.get("text") == "connected":
                            print("✅ Gemini Live connection established successfully!")
                        if data.get("type") == "error":
                            print(f"❌ Server reported error: {data.get('text')}")
                            sys.exit(1)
                    else:
                        print(f"Received Binary data ({len(msg)} bytes)")
                        print("✅ Received audio data from Gemini!")
                        # If we received audio, it means the pipeline is working.
                        sys.exit(0)
                except asyncio.TimeoutError:
                    print("Timed out waiting for message")
                    sys.exit(1)
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_ws())
