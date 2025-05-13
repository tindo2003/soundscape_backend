from celery import shared_task
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count
from .models import Concert
from .ticketmaster import TicketmasterAPI
from users.models import UserTopArtist, User

@shared_task
def update_concerts():
    """
    Periodically update the concert database with new events from Ticketmaster.
    This task should be scheduled to run every few hours.
    """
    tm_api = TicketmasterAPI()
    
    # Get all unique users
    users = User.objects.all()
    
    # Keep track of processed artists to avoid duplicates
    processed_artists = set()
    
    for user in users:
        try:
            # Get user's top artists
            artist_names = (
                UserTopArtist.objects.filter(user_id=user.spotify_id)
                .order_by("-time_collected")
                .values_list("artist__name", flat=True)
                .distinct()[:50]
            )
            
            for artist in artist_names:
                # Skip if we've already processed this artist
                if artist in processed_artists:
                    continue
                    
                processed_artists.add(artist)

                artist_user_count = UserTopArtist.objects.filter(
                    artist__name=artist
                ).values('user').distinct().count()
                base_popularity_score = min(artist_user_count / 10, 1.0)  # Cap at 1.0
                
                # Search for events
                events = tm_api.search_events(artist)
                
                for event_data in events:
                    processed_event = tm_api.process_event_data(event_data)
                    if not processed_event:
                        continue
                    
                    popularity_score = base_popularity_score # Start with base
                    # Adjust score based on price
                    if processed_event.price:
                        try:
                            min_price = float(processed_event.price.split('-')[0].strip().split()[0])
                            popularity_score += (100 - min_price) / 200  # Add up to 0.5 based on price
                        except (ValueError, IndexError):
                            pass
                    
                    # Update or create the concert
                    Concert.objects.update_or_create(
                        ticketmaster_id=processed_event.id,
                        defaults={
                            'event_name': processed_event.name,
                            'artist': ', '.join(processed_event.artists),
                            'venue': processed_event.venue,
                            'location': processed_event.location,
                            'date': datetime.strptime(processed_event.date, '%Y/%m/%d') if processed_event.date != 'TBA' else None,
                            'price_range': processed_event.price,
                            'image_url': processed_event.image,
                            'event_url': processed_event.url,
                            'genres': processed_event.genres,
                            'popularity_score': popularity_score,
                        }
                    )
                    
        except Exception as e:
            print(f"Error processing user {user.spotify_id}: {e}")
            continue 