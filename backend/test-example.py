import asyncio
import httpx
import json 
from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import MessageToDict

# ──────────────────────────────────────────────────────────
# 🛠️ CONFIGURATION ZONE: PASTE ANY URL OR CREDENTIALS HERE
# ──────────────────────────────────────────────────────────
TARGET_URL = "https://data.waltti.fi/jyvaskyla/api/gtfsrealtime/v1.0/feed/servicealert"
WALTTI_ID="5691861609493738"
WALTTI_SECRET="VxbkcxPlhuhJBttkrxkxCdF3BSUoJmXI"

# Name of the output file where data will be stored
OUTPUT_FILE = "gtfs_dump.json"


async def inspect_and_save_gtfs_feed(url: str, username: str = None, password: str = None):
    print(f"[Step 1] Requesting data from: {url}")
    
    # Apply basic authorization credentials if supplied
    auth = (username, password) if (username and password) else None
    
    try:
        # Fetch the binary wire format over HTTP
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, auth=auth)
            response.raise_for_status()
            raw_bytes = response.content
            
        print(f"[Step 2] Download complete. Size: {len(raw_bytes)} bytes.")
        
        # Universal Container: Parses ALL standard GTFS-RT feeds
        feed = gtfs_realtime_pb2.FeedMessage()
        
        print("[Step 3] Decompressing binary stream via Protocol Buffers...")
        feed.ParseFromString(raw_bytes)
        
        # Convert the structural Protobuf Object graph into a standard clean Python Dictionary
        feed_dict = MessageToDict(feed, preserving_proto_field_name=True)
        
        # ──────────────────────────────────────────────────────────
        # 💾 FILE STORAGE ZONE
        # ──────────────────────────────────────────────────────────
        print(f"[Step 4] Writing decoded data to text file: '{OUTPUT_FILE}'...")
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            # json.dump takes the dictionary and writes it cleanly formatted to the text file
            json.dump(feed_dict, f, indent=2, ensure_ascii=False)
            
        print(f"🎉 Success! Data completely stored.")
        
        # ──────────────────────────────────────────────────────────
        # 📺 CONSOLE PREVIEW (Displays basic stats in terminal)
        # ──────────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("                 QUICK CONSOLE SUMMARY                      ")
        print("=" * 60)
        header = feed_dict.get("header", {})
        entities = feed_dict.get("entity", [])
        
        print(f"• Spec Version: {header.get('gtfs_realtime_version', 'Unknown')}")
        print(f"• Server Timestamp (Unix): {header.get('timestamp', 'N/A')}")
        print(f"• Total Feed Elements Extracted: {len(entities)}")
        print(f". total number of entities: ,", len(entities))
        print("-" * 60)
        
       
        print(f"👉 Open up the file '{OUTPUT_FILE}' to see the full dataset ({len(entities)} items).")
        
    except httpx.HTTPStatusError as e:
        print(f"\n[HTTP Error]: Server responded with status code {e.response.status_code}")
        print(f"Response body context: {e.response.text}")
    except Exception as e:
        print(f"\n[Parsing Error]: Failed to inflate the binary bytes into a GTFS-RT schema.")
        print(f"Details: {e}")


if __name__ == "__main__":
    asyncio.run(inspect_and_save_gtfs_feed(TARGET_URL, WALTTI_ID, WALTTI_SECRET))