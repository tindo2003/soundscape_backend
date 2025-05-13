from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q
from .models import Concert
from users.models import User, UserTopArtist
from users.utils import decrypt_session_token

@api_view(["GET"])
def recs_events(request, num=10):
    session_cookie = request.COOKIES.get("session")
    if not session_cookie:
        return Response(
            {"error": "No session token provided."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    session_payload = decrypt_session_token(session_cookie)
    if not session_payload or not session_payload.userid:
        return Response(
            {"error": "Invalid or expired session."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    
    user_id = session_payload.spotify_id
    
    # Get user's top artists
    top_artists = (
        UserTopArtist.objects.filter(user_id=user_id)
        .order_by("-time_collected")
        .values_list("artist__name", flat=True)
        .distinct()[:50]
    )
    artist_names_list = list(top_artists)
    
    # Get upcoming concerts from the database that match user's top artists
    upcoming_concerts = Concert.objects.filter(
        Q(date__gte=timezone.now()) &
        Q(date__lte=timezone.now() + timedelta(days=90)) &
        Q(artist__in=artist_names_list)
    ).order_by('-popularity_score', 'date')[:num]
    
    # If we don't have enough concerts matching user's top artists,
    # get some additional popular concerts
    if len(upcoming_concerts) < num:
        additional_concerts = Concert.objects.filter(
            Q(date__gte=timezone.now()) &
            Q(date__lte=timezone.now() + timedelta(days=90))
        ).exclude(
            id__in=upcoming_concerts.values_list('id', flat=True)
        ).order_by('-popularity_score', 'date')[:num - len(upcoming_concerts)]
        
        upcoming_concerts = list(upcoming_concerts) + list(additional_concerts)
    
    # Convert to the expected format
    recommendations = [{
        'id': concert.ticketmaster_id,
        'eName': concert.artist,
        'venue': concert.venue,
        'location': concert.location,
        'date': concert.date.strftime('%Y/%m/%d'),
        'time': concert.date.strftime('%H:%M'),
        'price': concert.price_range,
        'imageUrl': concert.image_url,
        'eventUrl': concert.event_url,
    } for concert in upcoming_concerts]
    
    return Response(dict(data=recommendations)) 