from fastapi import APIRouter, Query
from typing import List, Optional
import httpx
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(
    prefix="/user",
    tags=["concerts"]
)

TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY")
TICKETMASTER_BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"

@router.get("/concerts/search")
async def search_concerts(
    latitude: float,
    longitude: float,
    radius: int = 50,
    keyword: Optional[str] = None,
    eventType: Optional[str] = None,
    artistIds: Optional[List[str]] = Query(None)
):
    try:
        params = {
            "apikey": TICKETMASTER_API_KEY,
            "latlong": f"{latitude},{longitude}",
            "radius": radius,
            "unit": "miles",
            "size": 20,
            "classificationName": "music"
        }
        
        if eventType and eventType != "all":
            params["segmentName"] = eventType
            
        if keyword:
            params["keyword"] = keyword

        async with httpx.AsyncClient() as client:
            response = await client.get(TICKETMASTER_BASE_URL, params=params)
            data = response.json()
            
            events = []
            for event in data.get("_embedded", {}).get("events", []):
                events.append({
                    "id": event["id"],
                    "artist": event["name"],
                    "venue": event["_embedded"]["venues"][0]["name"],
                    "date": event["dates"]["start"]["localDate"],
                    "time": event["dates"]["start"].get("localTime", ""),
                    "location": f"{event['_embedded']['venues'][0]['city']['name']}, {event['_embedded']['venues'][0]['state']['stateCode']}",
                    "price": f"${event['priceRanges'][0]['min']}" if "priceRanges" in event else "Price TBA",
                    "imageUrl": event["images"][0]["url"] if event["images"] else "",
                    "url": event["url"],
                    "attendingFriends": 0  # This would need to be implemented with your social features
                })
                
            return events
            
    except Exception as e:
        print(f"Error fetching concerts: {e}")
        return {"error": str(e)} 