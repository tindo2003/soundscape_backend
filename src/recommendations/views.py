from django.shortcuts import render
from recommendations.recommend_track import get_recommendation_from_cluster
from recommendations.pre_processing import read_pre_processed_data
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework import status
from users.models import UserTopTrack
import pandas as pd
import os
from django.db.models import Avg, Count
from recs.popularity_recommender import PopularityBasedRecs
from recs.content_based_recommender import ContentBasedRecs
from recs.event_recommender import EventRecs
from recommendations.models import SeededRecs
from users.models import UserTopTrack
from music.services import get_track
from users.services import get_sp
from rest_framework.decorators import api_view
from users.views import decrypt_session_token
from users.models import User, SoundscapeUser, Friendship
from django.db.models import Q
import requests
from rest_framework.decorators import api_view
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie


class RecommendationView(APIView):
    # Create your views here.
    def get(self, request, format=None):
        try:
            # Extract query parameters
            spotify_id = request.query_params.get("spotifyId")
            N = request.query_params.get("N", "10")

            if not N or not N.isdigit():
                raise ValidationError(
                    {"error": "The 'N' query parameter must be a valid integer."}
                )

            N = int(N)  # Convert N to an integer

            # Load data
            data_dir = os.path.abspath("/Volumes/Extreme SSD/data")
            playlist_df, tracks_df, playlist_tracks_df = read_pre_processed_data(
                "/Volumes/Extreme SSD/preprocessed_data"
            )

            # Process tracks dataframe
            tracks_df["id"] = tracks_df["track_uri"].apply(lambda x: x.split(":")[-1])

            # Load cluster data
            cluster_tracks_df = pd.read_csv(
                os.path.join(data_dir, "tracks_cluster.csv"), header=0
            )

            # Get all user tracks ordered by rank
            user_tracks = UserTopTrack.objects.filter(user_id=spotify_id).order_by(
                "-rank"
            )

            # Check each track until we find one in cluster_tracks_df
            current_song_id = None
            for user_track in user_tracks:
                track_id = user_track.track.track_id
                if track_id in cluster_tracks_df["id"].values:
                    current_song_id = track_id
                    break

            # If no match is found, select a fallback and notify the client
            if not current_song_id:
                fallback_track_id = cluster_tracks_df.sample(1).iloc[0]["track_id"]
                current_song_id = fallback_track_id
                return Response(
                    {
                        "message": "We couldn't find a matching track from your top tracks in our system. Recommendations are based on a fallback track.",
                        "recommendations": get_recommendation_from_cluster(
                            cluster_tracks_df, tracks_df, current_song_id, N=N
                        ).to_dict(orient="records"),
                    },
                    status=200,
                )

            # Get recommendations
            recommended_tracks = get_recommendation_from_cluster(
                cluster_tracks_df, tracks_df, current_song_id, N=N
            )

            # Get the name of the current song
            current_song_name = tracks_df[tracks_df["id"] == current_song_id][
                "track_name"
            ].values[0]

            # Return recommendations as JSON response
            return Response(
                {
                    "input": current_song_name,
                    "recommendations": recommended_tracks.to_dict(orient="records"),
                },
                status=200,
            )

        except ValidationError as e:
            return Response({"error": e.detail}, status=400)

        except FileNotFoundError as e:
            return Response({"error": f"File not found: {e}"}, status=500)

        except Exception as e:
            return Response(
                {"error": f"An unexpected error occurred: {str(e)}"}, status=500
            )


def chart(request, take=10):
    spotify_id = request.GET.get("spotifyId")
    res = PopularityBasedRecs().chart_top_tracks_by_country(spotify_id)
    print(res)
    return Response(res)


@api_view(["GET"])
# @cache_page(60 * 15)
# @vary_on_cookie
def recs_using_association_rules(request, user_id, take=10):
    """
    Queries the database for events that are
    related to the user_id, orders those by
    created, and returns a unique list of items
    """
    seeds = (
        UserTopTrack.objects.filter(user_id=user_id)
        .values_list("track_id", flat=True)
        .distinct()
    )
    print(len(seeds))

    """
    Queries the association rules and finds all rules where the source is among the content found in the active user's event log
    """
    rules = (
        SeededRecs.objects.filter(source__in=seeds)
        .exclude(target__in=seeds)
        .values("target")
        .annotate(confidence=Avg("confidence"))
        .order_by("-confidence")
    )
    rules = rules[:take]
    print("I HAVE ", len(rules), "RULES")
    print(user_id)
    recs = [{"id": rule["target"], "confidence": rule["confidence"]} for rule in rules]
    _, sp = get_sp(user_id)
    # we don't use Serializer here because recommended tracks may not appear in the db
    tracks = [get_track(sp, rec["id"]) for rec in recs]

    print("recs from association rules: \n{}".format(recs[:take]))
    # return Response(dict(data=list(recs)))
    return Response(dict(data=tracks))


@api_view(["GET"])
# @cache_page(60 * 15)
# @vary_on_cookie
def recs_cb(request, user_id, num=10):

    sorted_items = ContentBasedRecs().recommend_items(user_id, num)

    recs = {"user_id": user_id, "data": sorted_items}
    print("recs from cb: ", recs)
    _, sp = get_sp(user_id)
    # we don't use Serializer here because recommended tracks may not appear in the db
    tracks = [get_track(sp, rec[0]) for rec in recs["data"]]

    return Response(dict(data=tracks))


@api_view(["GET"])
def search_concerts(request):
    try:
        # Get current user from session
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
        
        current_user = User.objects.get(
            spotify_id=session_payload.spotify_id
        ).soundscape_user

        # Get search parameters
        latitude = request.GET.get("latitude")
        longitude = request.GET.get("longitude")
        radius = request.GET.get("radius", 50)
        keyword = request.GET.get("keyword")

        # Your existing Ticketmaster API call logic
        api_key = os.environ.get("TICKETMASTER_API_KEY")
        if not api_key:
            return Response(
                {"error": "Ticketmaster API key not configured"}, 
                status=500
            )

        params = {
            "apikey": api_key,
            "latlong": f"{latitude},{longitude}",
            "radius": radius,
            "classificationName": "music",
            "size": 20,
            "sort": "date,asc",
            "unit": "miles",
            "locale": "en-us",
            "includeFamily": "no",
        }

        if keyword:
            params["keyword"] = keyword

        response = requests.get(
            "https://app.ticketmaster.com/discovery/v2/events.json", 
            params=params
        )

        # Handle different status codes
        if response.status_code != 200:
            error_message = f"Ticketmaster API returned status code {response.status_code}"
            try:
                error_data = response.json()
                if error_data.get("errors"):
                    error_message += f": {error_data['errors']}"
            except:
                error_message += f": {response.text}"
            
            print(f"Error in search_concerts: {error_message}")
            return Response(
                {"error": error_message},
                status=status.HTTP_502_BAD_GATEWAY
            )

        data = response.json()
        
        if not data.get("_embedded", {}).get("events"):
            return Response([])

        events = data["_embedded"]["events"]
        concerts = []

        for idx, event in enumerate(events):
            event_id = event["id"]
            
            # Get attending friends logic
            attendees = SoundscapeUser.objects.filter(
                concert_attendances__concert_id=event_id
            ).exclude(user_id=current_user.user_id)

            # Get current user's friends
            friend_relationships = Friendship.objects.filter(
                Q(user1=current_user.profile) | Q(user2=current_user.profile)
            )

            friend_profiles = []
            for friendship in friend_relationships:
                if friendship.user1 == current_user.profile:
                    friend_profiles.append(friendship.user2)
                else:
                    friend_profiles.append(friendship.user1)

            # Filter attendees to only include friends
            friend_attendees = attendees.filter(profile__in=friend_profiles)

            # Format concert data
            concert = {
                "id": event_id,
                "artist": event["name"],
                "venue": event["_embedded"]["venues"][0]["name"],
                "date": event["dates"]["start"]["localDate"],
                "time": event["dates"]["start"].get("localTime", "Time TBA"),
                "location": f"{event['_embedded']['venues'][0]['city']['name']}, {event['_embedded']['venues'][0]['state']['stateCode']}",
                "price": (
                    f"${event['priceRanges'][0]['min']}+"
                    if event.get("priceRanges")
                    else "Price TBA"
                ),
                "imageUrl": event["images"][0]["url"] if event.get("images") else "",
                "eventUrl": event.get("url", ""),
                "attendingFriends": [
                    {
                        'user_id': str(attendee.user_id),
                        'username': attendee.username,
                        'pfp': attendee.pfp
                    }
                    for attendee in friend_attendees
                ]
            }
            concerts.append(concert)

        return Response(concerts)

    except Exception as e:
        print(f"Error in search_concerts: {str(e)}")
        return Response({"error": str(e)}, status=500)



@api_view(["GET"])
# @cache_page(60 * 15)
# @vary_on_cookie
def recs_events(request, num=10):
    session_cookie = request.COOKIES.get("session")
    if not session_cookie:
        return Response(
            {"error": "No session token provided."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    session_payload = decrypt_session_token(session_cookie)
    print(session_payload.model_dump())
    if not session_payload or not session_payload.userid:
        return Response(
            {"error": "Invalid or expired session."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    user_id = session_payload.spotify_id

    item = EventRecs().recommend_items(user_id, num)
    # item = EventRecs().recommend_items("tindooooo", num)

    return Response(dict(data=item))
