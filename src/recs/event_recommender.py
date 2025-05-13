import logging
from datetime import datetime, timedelta
from django.utils import timezone
import time
import os
from dotenv import load_dotenv
import requests
from geolib import geohash
from tqdm import tqdm
from django.db.models import Q

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "soundscape.settings")

import django

django.setup()

from users.models import UserTopArtist, User, ConcertAttendance, SoundscapeUser, Friendship
from concerts.models import Concert

load_dotenv()

def get_geo_hash(latitude=39.9526, longitude=-75.1652, precision=7):
    """
    Generates a GeoHash for given latitude and longitude.
    Default to Philly
    """
    return geohash.encode(latitude, longitude, precision)

class EventRecs:
    def recommend_items(self, spotify_id, num=10):
        """
        Get recommendations for a user based on their top tracks.
        """
        # Get the user's top tracks
        artist_names = (
            UserTopArtist.objects.filter(user_id=spotify_id)
            .order_by("-time_collected")
            .values_list("artist__name", flat=True)
            .distinct()[:50]
        )
        
        # an instance of Soundscape user
        current_user = User.objects.get(spotify_id=spotify_id).soundscape_user
        artist_names_list = list(artist_names)

        # Get upcoming concerts from the database that match user's top artists
        artist_query = Q()
        for artist in artist_names_list:
            artist_query |= Q(artist__icontains=artist)
            
        upcoming_concerts = Concert.objects.filter(
            Q(date__gte=timezone.now()) &
            Q(date__lte=timezone.now() + timedelta(days=90)) &
            artist_query
        ).order_by('-popularity_score', 'date')

        # If we don't have enough concerts matching user's top artists,
        # get some additional popular concerts
        if len(upcoming_concerts) < num:
            # Get IDs of concerts we already have
            existing_ids = set(upcoming_concerts.values_list('id', flat=True))
            
            # Get additional concerts excluding the ones we already have
            additional_concerts = Concert.objects.filter(
                Q(date__gte=timezone.now()) &
                Q(date__lte=timezone.now() + timedelta(days=90))
            ).exclude(
                id__in=existing_ids
            ).order_by('-popularity_score', 'date')
            
            # Combine the querysets and take the first num results
            all_concerts = list(upcoming_concerts) + list(additional_concerts)
            upcoming_concerts = all_concerts[:num]
        else:
            upcoming_concerts = list(upcoming_concerts[:num])

        # Convert to the expected format and add friend attendance information
        recommendations = []
        for concert in upcoming_concerts:
            # Get attending friends
            attendees = SoundscapeUser.objects.filter(
                concert_attendances__concert_id=concert.ticketmaster_id
            ).exclude(user_id=current_user.user_id)
            
            friend_relationships = Friendship.objects.filter(
                Q(user1=current_user.profile) | Q(user2=current_user.profile)
            )

            friend_profiles = []
            for friendship in friend_relationships:
                if friendship.user1 == current_user.profile:
                    friend_profiles.append(friendship.user2)
                else:
                    friend_profiles.append(friendship.user1)

            friendAttendees = attendees.filter(profile__in=friend_profiles)

            recommendation = {
                'id': concert.ticketmaster_id,
                'eName': concert.event_name,
                'artists': concert.artist,
                'venue': concert.venue,
                'location': concert.location,
                'date': concert.date.strftime('%Y/%m/%d'),
                'time': concert.date.strftime('%H:%M'),
                'price': concert.price_range,
                'genres': concert.genres,
                'imageUrl': concert.image_url,
                'eventUrl': concert.event_url,
                'attendingFriends': [
                    {
                        'user_id': str(attendee.user_id),
                        'username': attendee.username,
                        'pfp': attendee.pfp
                    }
                    for attendee in friendAttendees
                ]
            }
            recommendations.append(recommendation)

        return {"newEvents": recommendations}


if __name__ == "__main__":
    event_rec = EventRecs()
    res = event_rec.recommend_items("tindooooo")
    print(res)
