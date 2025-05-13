import os
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
import requests
from geolib import geohash
from dataclasses import dataclass
from typing import Optional, List

load_dotenv()

def get_geo_hash(latitude=39.9526, longitude=-75.1652, precision=7):
    """
    Generates a GeoHash for given latitude and longitude.
    Default to Philly
    """
    return geohash.encode(latitude, longitude, precision)

@dataclass
class TicketmasterEvent:
    id: str
    name: str
    artists: List[str]
    venue: str
    date: str
    time: str
    url: str
    image: str
    location: str
    price: str
    genres: List[str]

    @classmethod
    def from_api_response(cls, event_data: dict) -> Optional['TicketmasterEvent']:
        """
        Create a TicketmasterEvent from the API response data.
        
        Args:
            event_data (dict): Raw event data from Ticketmaster API
            
        Returns:
            Optional[TicketmasterEvent]: Event object or None if processing fails
        """
        try:
            # Process embedded data
            embedded = event_data.get("_embedded", {})
            
            # Process attractions (artists) - only get type 'attraction'
            artists = []
            for attraction in embedded.get("attractions", []):
                if attraction.get("type") == "attraction":
                    artists.append(attraction.get("name", ""))
            if len(artists) == 0:
                # if there is no artist, return None
                return None

            # Process venue information
            venue_info = {}
            for venue in embedded.get("venues", []):
                venue_info = {
                    "name": venue.get("name", ""),
                    "address": venue.get("address", {}).get("line1", ""),
                    "city": venue.get("city", {}).get("name", ""),
                    "state": venue.get("state", {}).get("name", ""),
                }
                break  # Take first venue

            # Process date information
            start = event_data.get("dates", {}).get("start", {})
            date_obj = None
            
            # Try to get date and time
            if "dateTime" in start:
                try:
                    date_obj = datetime.strptime(start["dateTime"], "%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    try:
                        date_obj = datetime.strptime(start["dateTime"], "%Y-%m-%dT%H:%M:%S%z")
                    except ValueError:
                        pass
            elif "localDate" in start:
                try:
                    date_obj = datetime.strptime(start["localDate"], "%Y-%m-%d")
                except ValueError:
                    pass

            # Format date and time strings
            date_str = date_obj.strftime("%Y/%m/%d") if date_obj else "TBA"
            time_str = date_obj.strftime("%H:%M") if date_obj else ""

            # Process price information
            price = ""
            price_ranges = event_data.get("priceRanges", [])
            if price_ranges:
                pr = price_ranges[0]
                min_price = pr.get("min")
                max_price = pr.get("max")
                currency = pr.get("currency")
                if min_price is not None and max_price is not None and currency:
                    price = f"{min_price}-{max_price} {currency}"
                elif min_price is not None and currency:
                    price = f"{min_price} {currency}"

            # Get the largest image
            images = event_data.get("images", [])
            image_url = cls.find_largest_image(images) if images else ""

            # Extract genres from classifications
            genres = set()
            for classification in event_data.get("classifications", []):
                if classification.get("primary", False):
                    if segment := classification.get("segment", {}):
                        if segment.get("name"):
                            genres.add(segment["name"])
                    if genre := classification.get("genre", {}):
                        if genre.get("name"):
                            genres.add(genre["name"])
                    if sub_genre := classification.get("subGenre", {}):
                        if sub_genre.get("name"):
                            genres.add(sub_genre["name"])

            return cls(
                id=event_data.get("id", ""),
                name=event_data.get("name", ""),
                artists=artists,
                venue=venue_info.get("name", ""),
                date=date_str,
                time=time_str,
                url=event_data.get("url", ""),
                image=image_url,
                location=f"{venue_info.get('address', '')}, {venue_info.get('city', '')}, {venue_info.get('state', '')}",
                price=price,
                genres=list(genres)
            )
        except Exception as e:
            logging.error(f"Error processing event data: {e}")
            return None

    @staticmethod
    def find_largest_image(images: List[dict]) -> str:
        """
        Find the largest image from a list of image objects.
        
        Args:
            images (list): List of image objects from Ticketmaster API
            
        Returns:
            str: URL of the largest image or empty string if no images
        """
        if not images:
            return ""

        largest_image = images[0]
        max_area = largest_image.get("width", 0) * largest_image.get("height", 0)

        for image in images[1:]:
            current_area = image.get("width", 0) * image.get("height", 0)
            if current_area > max_area:
                largest_image = image
                max_area = current_area

        return largest_image.get("url", "")

class TicketmasterAPI:
    def __init__(self):
        self.api_key = os.getenv("TICKETMASTER_API_KEY")
        self.base_url = os.getenv("TICKETMASTER_URL")
        if not self.api_key or not self.base_url:
            raise ValueError("Ticketmaster API key or URL not found in environment variables")

    def search_events(self, keyword, page=0, page_size=20):
        """
        Search for events using the Ticketmaster API.
        Rate limit: 5 requests per second
        Daily quota: 5000 API calls per day
        
        Args:
            keyword (str): The search keyword (usually artist name)
            page (int): Page number for pagination
            page_size (int): Number of results per page
            
        Returns:
            list: List of events or empty list if no results
        """
        params = {
            "apikey": self.api_key,
            "unit": "miles",
            "geoPoint": get_geo_hash(),
            "radius": 30,
            "page": page,
            "size": page_size,
            "keyword": keyword,
            "segmentId": "KZFzniwnSyZfZ7v7nJ"  # Music segment ID
        }

        max_retries = 3
        base_sleep_time = 0.2  # 200ms between requests to stay under 5 requests/second
        all_events = []

        for retry in range(max_retries):
            try:
                # Get first page
                response = requests.get(self.base_url, params=params)
                response_code = response.status_code

                if response_code in (200, 201):
                    data = response.json()
                    page_info = data.get("page", {})
                    total_results = page_info.get("totalElements", 0)
                    logging.debug(f"tmSearch() - results: {total_results}")

                    if total_results == 0:
                        logging.debug("tmSearch() - No Ticketmaster Results")
                        return []

                    # Process first page events
                    events = data.get("_embedded", {}).get("events", [])
                    all_events.extend(events)

                    # Get next page URL from _links
                    next_page_url = data.get("_links", {}).get("next", {}).get("href")
                    
                    # Continue fetching pages while next page URL exists
                    while next_page_url:
                        # Sleep to respect rate limit of 5 requests/second
                        time.sleep(base_sleep_time)
                        logging.debug(f"Getting next page: {next_page_url}")
                        
                        # Make request to next page URL
                        next_response = requests.get(next_page_url)
                        
                        if next_response.status_code in (200, 201):
                            next_data = next_response.json()
                            next_events = next_data.get("_embedded", {}).get("events", [])
                            all_events.extend(next_events)
                            
                            # Get next page URL
                            next_page_url = next_data.get("_links", {}).get("next", {}).get("href")
                        elif next_response.status_code == 429:  # Rate limit exceeded
                            sleep_time = base_sleep_time * (2 ** retry)  # Exponential backoff
                            logging.warning(f"Rate limit exceeded. Retrying in {sleep_time} seconds...")
                            time.sleep(sleep_time)
                            continue
                        else:
                            logging.error(
                                f"tmSearch() error - Next Page Response Code {next_response.status_code} {next_response.text}"
                            )
                            break

                    return all_events

                elif response_code == 429:  # Rate limit exceeded
                    sleep_time = base_sleep_time * (2 ** retry)  # Exponential backoff
                    logging.warning(f"Rate limit exceeded. Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                    continue
                else:
                    logging.error(f"tmSearch() error - Response Code {response_code} {response.text}")
                    return []

            except Exception as err:
                logging.error(f"tmSearch() error: {err}")
                if retry < max_retries - 1:  # Don't sleep on the last retry
                    time.sleep(base_sleep_time * (2 ** retry))
                    continue
                return []

        logging.error("Max retries exceeded for rate limit")
        return []

    def process_event_data(self, event_data):
        """
        Process raw event data from Ticketmaster API into a TicketmasterEvent object.
        
        Args:
            event_data (dict): Raw event data from Ticketmaster API
            
        Returns:
            Optional[TicketmasterEvent]: Event object or None if processing fails
        """
        return TicketmasterEvent.from_api_response(event_data) 

if __name__ == "__main__":
    tm = TicketmasterAPI()
    results = tm.search_events("The Weeknd")
    print(results, len(results))
    tmp = TicketmasterEvent.from_api_response(results[0])
    print(tmp)