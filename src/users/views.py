# views.py
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie, vary_on_headers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Exists, OuterRef
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.decorators import api_view
import bcrypt
import jwt
from typing import Optional, Dict
import os
from dotenv import load_dotenv
from pydantic import BaseModel
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from django.core.exceptions import ValidationError
from django.db.models import F
from .services import _update_user_access_token
import django
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from collections import defaultdict
from functools import wraps
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync






def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()  # Generate a random salt
    hashed = bcrypt.hashpw(password.encode(), salt)  # Hash the password
    return hashed.decode()  # Convert bytes to string for storage


from .models import (
    User,
    SoundscapeUser,
    UserTopArtist,
    UserTopTrack,
    UserSavedAlbums,
    UserGenreListening,
    Reviews,
    FriendRequest,
    Friendship,
    Notification,
    Chat,
    Message
)
from music.models import Artist, Track, Album, Genre
from .serializers import (
    UserSerializer,
    UserTopArtistSerializer,
    UserTopTrackSerializer,
    UserSavedAlbumsSerializer,
    ReviewSerializer,
    SoundscapeUserSerializer
)

from music.services import save_or_update_track, get_or_create_artist
from users.services import (
    fetch_and_save_user_top_tracks,
    fetch_and_save_user_top_artists,
    get_user_recently_listened,
    fetch_and_store_top_genres
)
from music.serializers import GenreSerializer, TrackSerializer
import logging

logger = logging.getLogger(__name__)

from urllib.parse import urlencode
from django.shortcuts import redirect
from django.utils import timezone
from datetime import timedelta
import requests
from dotenv import load_dotenv
import tekore as tk
import os

load_dotenv()
client_id = os.getenv("spotify_client_id")
client_secret = os.getenv("spotify_client_secret")
redirect_uri = os.getenv("spotify_redirect_uri")
cred = tk.RefreshingCredentials(client_id, client_secret, redirect_uri)
from django.db import transaction



def fetch_and_save_spotify_user(access_token, refresh_token=None, expires_in=None):
    try:
        spotify = tk.Spotify(access_token)
        current_user = spotify.current_user()
    except tk.HTTPError as e:
        return None, Response(
            {"error": "Failed to fetch user data from Spotify", "details": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Prepare user data
    user_data = {
        "display_name": current_user.display_name,
        "email": current_user.email,
        "country": current_user.country,
        "explicit_content": (
            current_user.explicit_content.filter_enabled
            if current_user.explicit_content
            else False
        ),
        "external_url": current_user.external_urls.get("spotify"),
        "followers_count": (
            current_user.followers.total if current_user.followers else 0
        ),
        "href": current_user.href,
        "product": current_user.product,
        "uri": current_user.uri,
    }

    if refresh_token and expires_in:
        user_data.update(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_expires": timezone.now() + timedelta(seconds=expires_in),
            }
        )

    user, created = User.objects.update_or_create(
        spotify_id=current_user.id, defaults=user_data
    )

    return user, None


class SpotifyCurrentUserView(APIView):
    """
    View to get current user's Spotify information.
    """

    def post(self, request, format=None):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return Response(
                {"error": f"Authorization header with Bearer token required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        access_token = auth_header.split(" ")[1]

        user, error_response = fetch_and_save_spotify_user(access_token)
        if error_response:
            return error_response

        serializer = UserSerializer(user)
        return Response(serializer.data)


class UserTopArtistsView(APIView):
    """
    View to get user's top artists and save them to the database.
    """

    def post(self, request, format=None):
        # Get time_range from query parameters (default to 'medium_term')
        time_range = request.query_params.get("time_range", "short_term")
        print("my time range", time_range)

        # Validate time_range
        if time_range not in ["long_term", "medium_term", "short_term"]:
            return Response(
                {"error": "Invalid time_range parameter"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get the Spotify access token
        spotify_id = request.data.get("spotifyId")
        if not spotify_id:
            print("spotify_id is required")
            return Response(
                {"error": "spotify_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Query the User database for the access token
        sp, user = verify_spotify_user(request)

        try:
            fetch_and_save_user_top_artists(user, sp)
            # Retrieve saved top artists for the user
            user_top_artists = UserTopArtist.objects.filter(
                user=user, time_range=time_range
            ).order_by("rank")
            serializer = UserTopArtistSerializer(user_top_artists, many=True)
            return Response(serializer.data)
        except tk.HTTPError as e:
            print('violentacrez')
            return Response(
                {
                    "error": "Failed to fetch top artists from Spotify",
                    "details": str(e),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class UserTopTracksView(APIView):
    """
    View to get user's top tracks and save them to the database.
    """
    @method_decorator(cache_page(60 * 60 * 2))
    #@method_decorator(vary_on_cookie)
    def post(self, request, format=None):
        print('hello')
        # Get time_range from query parameters (default to 'medium_term')
        time_range = request.query_params.get("time_range", "short_term")
        # Validate time_range
        if time_range not in ["long_term", "medium_term", "short_term"]:
            return Response(
                {"error": "Invalid time_range parameter"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sp, user = verify_spotify_user(request)
        # Fetch user's top tracks
        try:
            fetch_and_save_user_top_tracks(user, sp)

            # Retrieve saved top tracks for the user
            user_top_tracks = UserTopTrack.objects.filter(
                user=user, time_range=time_range
            ).order_by("rank")

            serializer = UserTopTrackSerializer(user_top_tracks, many=True)
            return Response(serializer.data)
        except tk.HTTPError as e:
            return Response(
                {"error": "Failed to fetch top tracks from Spotify", "details": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


from django.core.exceptions import ObjectDoesNotExist
import logging

logger = logging.getLogger(__name__)




# avoids repeat authentication code for confirming identity of current user
def verify_spotify_user(request):
    # Get the Spotify access token
    print('verify_spotify_user function')
    spotify_id = request.data.get("spotifyId")
    if not spotify_id:
        return Response(
            {"error": "spotify_id is required"}, status=status.HTTP_400_BAD_REQUEST
        )


    print('successfully retrieved spotify_id')
    # Query the User database for the access token
    access_token = None
    try:
        user = User.objects.get(spotify_id=spotify_id)
        access_token = user
        refresh_token = user.refresh_token
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    print('access token', access_token)
    # Initialize Tekore Spotify client
    try:
        spotify = tk.Spotify(access_token)
        current_user = spotify.current_user()
    except tk.HTTPError as e:
        if e.response.status_code == 401:  # Unauthorized, token might be expired
            try:
                print("invalid access token :()")
                # Refresh the token using the refresh token
                refreshing_token = cred.refresh_user_token(refresh_token)
                spotify = tk.Spotify(refreshing_token.access_token)
                print("my new access token is ", refreshing_token.access_token)
                # Update the database with the new token
                _update_user_access_token(spotify_id, refreshing_token.access_token)

                # return new_token.access_token

            except tk.HTTPError as refresh_error:
                # Handle cases where refresh token is also invalid
                print(f"Error refreshing token: {refresh_error}")
                return Response(
                    {"error": f"Error refreshing token: {refresh_error}"},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            # Handle other HTTP errors
            print(f"Error using access token: {e}")
            return Response(
                {"error": f"Error using access token: {e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Ensure user exists in our database
    user, _ = User.objects.get_or_create(spotify_id=spotify_id)
    return spotify, user


class UserSavedAlbumsView(APIView):
    """
    View to get user's saved albums and put them in the database.
    """

    def post(self, request, format=None):

        spotify, user = verify_spotify_user(request)
        print(user)
        # Fetch user's top tracks
        try:
            user_saved_albums = spotify.saved_albums(limit=10)
            # print(user_saved_albums)
            saved_albums = user_saved_albums.items
        except tk.HTTPError as e:
            return Response(
                {
                    "error": "Failed to fetch saved albums from Spotify",
                    "details": str(e),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # print(saved_albums)
        # print("--------START OF SAVED ALBUMS---------")
        # for album in saved_albums:
        #     print(user, album.album.id)
        # print("--------END OF SAVED ALBUMS---------")
        # print(len(saved_albums))

        for album in saved_albums:
            album_data = {
                "album_id": album.album.id,
                "name": album.album.name,
                "album_type": album.album.album_type,
                "release_date": album.album.release_date,
                "release_date_precision": album.album.release_date_precision,
                "total_tracks": album.album.total_tracks,
                "spotify_url": album.album.external_urls.get("spotify"),
                "href": album.album.href,
                "uri": album.album.uri,
                "art": album.album.images[0].url if album.album.images else None,
            }
            # print(album_data)
            try:
                with transaction.atomic(savepoint=False):
                    album_obj, _ = Album.objects.update_or_create(
                        album_id=album.album.id, defaults=album_data
                    )
            except Exception as e:
                print(f"Transaction failed: {e}")
                continue

            # Save track to Track model
            # print("HIiiiii", album.images[0].url)
            saved_album_data = {
                "type": album.album.type,
                "spotify_url": album.album.external_urls.get("spotify"),
                "popularity": album.album.popularity,
            }
            try: 
              UserSavedAlbums.objects.update_or_create(
                  album=album_obj, user=user, defaults=saved_album_data
              )
            except django.db.utils.OperationalError as e:
              if "SAVEPOINT" in str(e):
                print('chunghciungchung')
                continue
              else:
                raise   
                

        # Retrieve saved albums for the user
        the_user_saved_albums = UserSavedAlbums.objects.filter(user=user).order_by(
            "id"
        )[:10]

        serializer = UserSavedAlbumsSerializer(the_user_saved_albums, many=True)
        return Response(serializer.data)


class SpotifyLoginView(APIView):
    """
    Redirects the user to Spotify's authorization page.
    """

    def get(self, request, format=None):
        scopes = "user-read-private user-read-email user-top-read user-library-read"

        params = {
            "response_type": "code",
            "client_id": os.getenv("spotify_client_id"),
            "scope": scopes,
            "redirect_uri": os.getenv("spotify_redirect_uri"),
            "show_dialog": "false",
        }
        url = "https://accounts.spotify.com/authorize?" + urlencode(params)
        return Response({"redirect_url": url}, status=status.HTTP_200_OK)


def _link_spotify_account(user_id, spotify_profile):
    """
    Attempts to link a spotify_profile to a SoundscapeUser.

    Args:
        user_id (UUID): The user_id of the SoundscapeUser trying to link a Spotify account.
        spotify_profile (object): An object representing the Spotify profile,
                                which must have a unique attribute 'spotify_id'.

    Raises:
        ValidationError: If the spotify_profile is already linked to a different SoundscapeUser.

    Returns:
        SoundscapeUser: The updated SoundscapeUser instance.
    """
    try:
        existing_user = SoundscapeUser.objects.get(
            profile__spotify_id=spotify_profile.spotify_id
        )
        # If the found user is not the same as the one attempting to link, raise an error.
        if str(existing_user.user_id) != str(user_id):
            raise ValidationError(
                f"Spotify account is already linked to another Soundscape account with email {existing_user.email}. Please sign in with that account."
            )
    except SoundscapeUser.DoesNotExist:
        # No existing link found; it's safe to proceed.
        pass

    # Retrieve the SoundscapeUser trying to link their Spotify account.
    try:
        soundscape_user = SoundscapeUser.objects.get(user_id=user_id)
    except SoundscapeUser.DoesNotExist:
        raise ValidationError("Soundscape user does not exist.")

    # Link the Spotify profile to the SoundscapeUser.
    soundscape_user.profile = spotify_profile
    soundscape_user.save()
    return soundscape_user


class SpotifyCallbackView(APIView):
    """
    Handles the redirect from Spotify after authorization.
    """

    def get(self, request, format=None):
        code = request.query_params.get("code")

        request.session.pop("spotify_auth_state", None)

        token_url = "https://accounts.spotify.com/api/token"
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": os.getenv("spotify_redirect_uri"),
            "client_id": os.getenv("spotify_client_id"),
            "client_secret": os.getenv("spotify_client_secret"),
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        response = requests.post(token_url, data=payload, headers=headers)
        if response.status_code != 200:
            return Response(
                {"error": "Failed to get token"}, status=status.HTTP_400_BAD_REQUEST
            )

        token_info = response.json()
        access_token = token_info.get("access_token")
        refresh_token = token_info.get("refresh_token")
        expires_in = token_info.get("expires_in")  # In seconds

        spotify_profile, error_response = fetch_and_save_spotify_user(
            access_token, refresh_token=refresh_token, expires_in=expires_in
        )
        if error_response:
            return error_response

        serializer = UserSerializer(spotify_profile)
        user_data = serializer.data

        # Extract the spotify_id
        spotify_id = user_data.get("spotify_id")

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
        userid = session_payload.userid

        try:
            soundscape_user = SoundscapeUser.objects.get(user_id=userid)
        except SoundscapeUser.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            soundscape_user = _link_spotify_account(userid, spotify_profile)
        except ValidationError as e:
            print(e)
            query_params = urlencode({"error": str(e)})
            # Redirect to the dashboard with the error message
            return redirect(f"http://localhost:3000/dashboard?{query_params}")

        # --- Re-generate the JWT token with updated Spotify info ---
        token, expires_at = generate_jwt_token(soundscape_user)

        redirect_url = f"http://localhost:3000?spotify_id={spotify_id}"
        response = redirect(redirect_url)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            secure=True,
            samesite="Lax",
            expires=expires_at,
        )
        return response


class TopGenresView(APIView):
    def get(self, request):
        # Aggregate listen counts for each genre
        # Get the Spotify access token
        session_cookie = request.COOKIES.get("session")
        if not session_cookie:
            return Response(
                {"error": "No session token provided."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        session_payload = decrypt_session_token(session_cookie)
        print("top genre", session_payload.model_dump())
        if not session_payload or not session_payload.userid:
            return Response(
                {"error": "Invalid or expired session."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = User.objects.get(spotify_id=session_payload.spotify_id)
        spotify_id = user.spotify_id
        fetch_and_store_top_genres(user)
        top_genres = (
            UserGenreListening.objects.values("genre__name")  # Group by genre
            .filter(user=spotify_id)
            .annotate(
                total_listens=Sum("listen_count")
            )  # Sum listen counts for each genre
            .order_by("-total_listens")  # Order by listen count in descending order
        )
        # print("top genre view", top_genres)

        # Get Genre objects for the top genres
        genre_names = [entry["genre__name"] for entry in top_genres]
        # print(genre_names)

        return Response(genre_names, status=status.HTTP_200_OK)


# this function does not interact with spotify API: It collects the user's top songs from the database directly.
class SongsSearch(APIView):
    def get(self, request):
        # Aggregate listen counts for each genre
        # Get the Spotify access token

        print("we we fsdf;oiadsjiofadpjoisf here here")
        query = request.query_params.get("query")
        spotify_id = request.query_params.get("spotifyId")

        print(spotify_id)
        if not spotify_id:
            print("spotify_id is required")
            return Response(
                {"error": "spotify_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        tracks = Track.objects.filter(name__startswith=query)

        # print('Testing Query Result')
        # for track in tracks:
        #     print(track.name)

        # print(top_genres)

        # Get Genre objects for the top genres
        # Serialize the queryset
        serialized_tracks = None
        if len(tracks) > 8:
            serialized_tracks = TrackSerializer(tracks[:8], many=True)
        else:
            serialized_tracks = TrackSerializer(tracks, many=True)

        # Return the serialized data as a JSON response
        return Response(serialized_tracks.data)


# this function does not interact with spotify API: It collects the user's top songs from the database directly.
class TopSongsForReviewPage(APIView):
    def get(self, request):
        # Aggregate listen counts for each genre
        # Get the Spotify access token

        print("we we here here")
        vis = request.query_params.get("version")
        spotify_id = request.query_params.get("spotifyId")

        print(spotify_id)
        if not spotify_id:
            print("spotify_id is required")
            return Response(
                {"error": "spotify_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        tracks = Track.objects.filter(
            track_id__in=UserTopTrack.objects.filter(user_id=spotify_id).values_list(
                "track_id", flat=True
            )
        )

        # print('Testing Query Result')
        # for track in tracks:
        #     print(track.name)

        # print(top_genres)

        # Get Genre objects for the top genres
        # Serialize the queryset
        serialized_tracks = None
        if vis == "recent":
            if (len(tracks) < 8):
                serialized_tracks = TrackSerializer(
                tracks, many=True
            )
            else: 
              serialized_tracks = TrackSerializer(
                tracks[len(tracks) - 8 : len(tracks)], many=True
            )
        else:
            serialized_tracks = TrackSerializer(tracks[:8], many=True)

        # Return the serialized data as a JSON response
        return Response(serialized_tracks.data)


class RecentlyListened(APIView):
    def get(self, request):

        spotify_id = request.query_params.get("spotifyId")
        vis = request.query_params.get("version")

        print(spotify_id)
        if not spotify_id:
            print("spotify_id is required")
            return Response(
                {"error": "spotify_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            get_user_recently_listened(spotify_id)
            # track_ids = UserTopTrack.objects.filter(user=spotify_id, recently_listened=1).values_list('track_id', flat=True)

            user_top_tracks = UserTopTrack.objects.filter(user=spotify_id, recently_listened=1).annotate(
                review_exists=Exists(
                    Reviews.objects.filter(user_id=spotify_id, track_id=OuterRef('track_id'))
                )
            ).filter(review_exists=False)

    # Extract track_ids from these filtered UserTopTrack rows
            track_ids = user_top_tracks.values_list('track_id', flat=True)
            # Retrieve all Track entries that have an id in the list of track_ids
            tracks = Track.objects.filter(track_id__in=track_ids)
            serializer = TrackSerializer(tracks[:10], many=True)
            return Response(serializer.data)
        
        except Exception as e:
            print("lemme see this")
            return Response(
                {"error": f"An unexpected error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# fetches the class with specified song Id from the database
class FetchSingleTrack(APIView):
    def get(self, request):
        # Aggregate listen counts for each genre
        # Get the Spotify access token

        print("hi how are you")
        spotify_id = request.query_params.get("spotifyId")

        print(spotify_id)
        if not spotify_id:
            print("spotify_id is required")
            return Response(
                {"error": "spotify_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        id_field = request.query_params.get("trackId")
        track = Track.objects.get(track_id=id_field)

        # print('Testing Query Result')
        # for track in tracks:
        #     print(track.name)

        # print(top_genres)

        # Get Genre objects for the top genres
        # Serialize the queryset
        serialized_tracks = TrackSerializer(track)

        # Return the serialized data as a JSON response
        return Response(serialized_tracks.data)


class PutReviewInDB(APIView):
    def post(self, request, format=None):

        print("trusted- hi how are you")
        spotify_id = request.data.get("user")

        print(spotify_id)
        if not spotify_id:
            print("spotify_id is required")
            return Response(
                {"error": "spotify_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        data = request.data
        track = data.get("track")
        user = data.get("user")
        text = data.get("text")
        rating = data.get("rating")
        timestamp = data.get("timestamp")

        try:
            # Update or create a review in the database
            review, created = Reviews.objects.update_or_create(
                track_id=track,
                user_id=user,
                defaults={
                    "un_id": user + "," + track,
                    "text": text,
                    "rating": rating,
                    "timestamp": timestamp,
                },
            )

            print("digbert")

            # Return success response
            if created:
                print("created")
                return Response(
                    {
                        "message": "Review created successfully.",
                        "status": status.HTTP_201_CREATED,
                    }
                )
            else:
                print("not created")
                return Response(
                    {
                        "message": "Review updated successfully.",
                        "status": status.HTTP_200_OK,
                    }
                )
        except Exception as e:
            print("exception?")
            except_message = str(e)
            if "1305" in except_message:
                return Response(
                    {
                        "message": "Review created successfully.",
                        "status": status.HTTP_201_CREATED,
                    }
                )
            print("Error saving review:", str(e))
            return Response(
                {
                    "error": "An error occurred while saving the review.",
                    "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                }
            )


class GetReviewByUser(APIView):
    def get(self, request):
        spotify_id = request.query_params.get("spotifyId")

        print(spotify_id)
        if not spotify_id:
            print("spotify_id is required")
            return Response(
                {
                    "error": "spotify_id is required",
                    "status": status.HTTP_400_BAD_REQUEST,
                }
            )

        # Retrieve all reviews for the given song_id
        reviews = (
            Reviews.objects.filter(user_id=spotify_id)
            .order_by("-timestamp")
            # .values("un_id", "user_id", "text", "rating", "timestamp")
        )

        # tracks = (
        #     Reviews.objects.filter(user_id=spotify_id)
        #     .order_by("-timestamp")
        #     .select_related("track_id")
        #     .values_list("track_id__name", flat=True)
        #     .distinct()
        # )

        # Convert QuerySet to a list of dictionaries
        reviews_list = list(reviews)
        # tracks_list = list(tracks)

        # for review, track in zip(reviews_list, tracks_list):
        #     review["tracks"] = track
        #     print(review["tracks"])
        serialized_reviews = ReviewSerializer(reviews_list[:10], many=True)

        return Response(serialized_reviews.data)

class GetReviewBySong(APIView):
    def get(self, request):
        print("trusted- hi how are you")
        spotify_id = request.query_params.get("spotifyId")

        print(spotify_id)
        if not spotify_id:
            print("spotify_id is required")
            return Response(
                {
                    "error": "spotify_id is required",
                    "status": status.HTTP_400_BAD_REQUEST,
                }
            )
        song_id = request.query_params.get("track")

        # Retrieve all reviews for the given song_id
        reviews = (
            Reviews.objects.filter(track_id=song_id)
            .order_by("-timestamp")
            .values("un_id", "user_id", "text", "rating", "timestamp")
        )

        # Convert QuerySet to a list of dictionaries
        reviews_list = list(reviews)
        serialized_reviews = ReviewSerializer(reviews_list[:10], many=True)

        return Response(serialized_reviews.data)
    

class UpdateSocialMedia(APIView):
  def post(self, request):
      # Retrieve query parameters
      spotifyId = request.data.get("spotifyId")
      x = request.data.get("x")
      instagram = request.data.get("instagram")
      youtube = request.data.get("youtube")
      # Check that the required query parameter is provided
      if not spotifyId:
          return Response(
              {"error": "spotifyId query parameter is required."},
              status=status.HTTP_400_BAD_REQUEST,
          )

      try:
          # Retrieve the user based on spotifyId
          user = SoundscapeUser.objects.get(profile_id=spotifyId)
      except SoundscapeUser.DoesNotExist:
          return Response(
              {"error": "User not found."},
              status=status.HTTP_404_NOT_FOUND,
          )

      # Update the fields only if a new value is provided
      if x is not None:
          user.x = x
          user.save(update_fields=["x"])

      if instagram is not None:
          user.instagram = instagram
          user.save(update_fields=["instagram"])

      if youtube is not None:
          user.youtube = youtube
          user.save(update_fields=["youtube"])

      # Return the unchanged fields along with the updated pfp field
      returned_profile_id = user.profile.spotify_id if user.profile else ""
      return Response(
          {
              "name": user.username,
              "profile_id": returned_profile_id,
              "timestamp": user.timestamp,
              "email": user.email,
              "pfp": user.pfp,
              "x": user.x,
              "instagram": user.instagram,
              "youtube": user.youtube
          },
          status=status.HTTP_200_OK,
      )

class GetFriendRecs(APIView):
    def get(self, request):
      # Retrieve query parameter
      spotifyId = request.query_params.get('spotifyId')
      if not spotifyId:
          return Response({'error': 'Missing spotifyId parameter'}, status=400)

      # 1. Get friends of the current user
      friendships = Friendship.objects.filter(Q(user1_id=spotifyId) | Q(user2_id=spotifyId))
      friend_ids = set()
      for friendship in friendships:
          # Add the friend which is not the current user
          if friendship.user1_id == spotifyId:
              friend_ids.add(friendship.user2_id)
          else:
              friend_ids.add(friendship.user1_id)
      
      # 2. Query all SoundscapeUser and filter out friends and self
      non_friend_users = SoundscapeUser.objects.exclude(profile_id__in=friend_ids).exclude(profile_id=spotifyId)
      
      # 3. Prepare the current user's top genres and artists.
      # (Assuming UserGenreListening has a 'genre' field and UserTopArtist has an 'artist' field.)
      current_user_genres = set(
          UserGenreListening.objects.filter(user_id=spotifyId)
                                    .order_by('-listen_count')
                                    .values_list('genre_id', flat=True)[:25]
      )
      current_user_artists = set(
          UserTopArtist.objects.filter(user_id=spotifyId)
                              .order_by('rank')
                              .values_list('artist_id', flat=True)[:25]
      )
      
      recommendations = []
      # 4. Iterate over non-friends and compute similarity scores.
      for candidate in non_friend_users:
          candidate_id = candidate.profile_id

          # Get candidate's top genres and compute overlap with current user.
          candidate_genres = set(
              UserGenreListening.objects.filter(user_id=candidate_id)
                                        .order_by('-listen_count')
                                        .values_list('genre_id', flat=True)[:25]
          )
          genre_similarity = len(current_user_genres.intersection(candidate_genres))
          
          # Get candidate's top artists and compute overlap.
          candidate_artists = set(
              UserTopArtist.objects.filter(user_id=candidate_id)
                                  .order_by('rank')
                                  .values_list('artist_id', flat=True)[:25]
          )
          artist_similarity = len(current_user_artists.intersection(candidate_artists))
          
          # Combine the two scores equally. (Here we use a simple sum.)
          similarity_score = genre_similarity + artist_similarity
          
          recommendations.append({
              'user': candidate, 
              'similarity_score': similarity_score,
              'genre_similarity': genre_similarity,
              'artist_similarity': artist_similarity,
          })
      
      # 5. Sort recommendations by similarity score in descending order and take the top 2.
      recommendations.sort(key=lambda x: x['similarity_score'], reverse=True)
      top_recommendations = recommendations[:2]
      
      top_user_ids = [rec['user'].user_id for rec in top_recommendations]


      top_users_queryset = SoundscapeUser.objects.filter(user_id__in=top_user_ids)
      serializer = SoundscapeUserSerializer(top_users_queryset, many=True)
      return Response(serializer.data)

class GetSoundScapeProfile(APIView):
  def get(self, request):
      print('hilo hawaii')
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
      userid = session_payload.spotify_id

    #   userid = request.query_params.get("spotifyId")
      User = SoundscapeUser.objects.get(profile_id=userid)
      returned_profile_id = User.profile.spotify_id if User.profile else ""
      return Response(
          {"name": User.username,
          "profile_id": returned_profile_id,
          "user_id": User.user_id,
          "timestamp": User.timestamp,
          "email": User.email,
          "pfp": User.pfp,
          "x": User.x,
          "instagram": User.instagram,
          "youtube": User.youtube
          },
          status=status.HTTP_200_OK,
      )
  def put(self, request):
      # Retrieve query parameters
      spotifyId = request.query_params.get("spotifyId")
      new_pfp = request.query_params.get("pfp")

      # Check that the required query parameter is provided
      if not spotifyId:
          return Response(
              {"error": "spotifyId query parameter is required."},
              status=status.HTTP_400_BAD_REQUEST,
          )

      try:
          # Retrieve the user based on spotifyId
          user = SoundscapeUser.objects.get(profile_id=spotifyId)
      except SoundscapeUser.DoesNotExist:
          return Response(
              {"error": "User not found."},
              status=status.HTTP_404_NOT_FOUND,
          )

      # Update the 'pfp' field only if a new value is provided
      if new_pfp is not None:
          user.pfp = new_pfp
          user.save(update_fields=["pfp"])

      # Return the unchanged fields along with the updated pfp field
      returned_profile_id = user.profile.spotify_id if user.profile else ""
      return Response(
          {
              "name": user.username,
              "profile_id": returned_profile_id,
              "timestamp": user.timestamp,
              "email": user.email,
              "pfp": user.pfp,
          },
          status=status.HTTP_200_OK,
      )




############################################################################################################
###### User authentication with JWT #################################################################
######
############################################################################################################
class SessionPayload(BaseModel):
    userid: str
    exp: float
    spotify_id: Optional[str] = None


def generate_jwt_token(user):
    expires_at = timezone.now() + timedelta(
        hours=int(os.getenv("JWT_EXPIRATION_HOURS"))
    )
    payload = {
        "userid": str(user.user_id),
        "exp": expires_at.timestamp(),
    }
    print("payload", payload)

    # Try to include the spotifyid in the token payload
    try:
        spotify_profile = user.profile
        payload["spotify_id"] = spotify_profile.spotify_id
    except (User.DoesNotExist, AttributeError):
        payload["spotify_id"] = None

    token = jwt.encode(
        payload, os.getenv("JWT_SECRET"), algorithm=os.getenv("JWT_ALGORITHM")
    )
    return token, expires_at


def decrypt_session_token(token: str) -> Optional[SessionPayload]:
    try:
        # Replace "HS256" with your algorithm, and key with your secret key.
        payload = jwt.decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        return SessionPayload(**payload)
    except jwt.ExpiredSignatureError as error:
        print("Failed to decrypt session:", error)
        return None


@api_view(["POST"])
def signin(request):
    data = request.data
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return Response(
            {"error": "Username and password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        soundscape_user = SoundscapeUser.objects.get(email=email)
    except SoundscapeUser.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    if not soundscape_user.isVerified:
        return Response(
            {"error": "Email is not verified"},
            status=status.HTTP_403_FORBIDDEN,
        )
    
    # 2. Check password
    if not bcrypt.checkpw(password.encode(), soundscape_user.password.encode()):
        return Response(
            {"error": "Invalid password"}, status=status.HTTP_401_UNAUTHORIZED
        )

    token, expires_at = generate_jwt_token(soundscape_user)

    response = Response(
        {"message": "Signin successful"},
        status=status.HTTP_200_OK,
    )

    # 6. Set cookies for session JWT and optional Spotify ID
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,  # Keep True for session token security unless JS access is essential
        secure=False,   # <<< Allows cookie over HTTP
        samesite='Lax', # <<< Behaves well with HTTP, allows same-site and top-level cross-site
        expires=expires_at,
    )

    return response


def send_email(email: str, email_type: str, user_id: int):
    """
    email: Recipient's email address
    email_type: 'VERIFY' or 'RESET'
    user_id: The ID of the user to send the email to
    """
    try:
        # 1) Create a hashed token from user ID (similar to your bcrypt usage in Node.js)
        hashed_token_bytes = bcrypt.hashpw(str(user_id).encode("utf-8"), bcrypt.gensalt(10))
        hashed_token = hashed_token_bytes.decode("utf-8")

        # 2) Update the user in the database
        user = SoundscapeUser.objects.get(user_id=user_id)

        if email_type == "VERIFY":
            user.verifyToken = hashed_token
            user.verifyTokenExpiry = timezone.now() + timedelta(hours=1)
            subject = "Verify your email"
        elif email_type == "RESET":
            user.forgotPasswordToken = hashed_token
            user.forgotPasswordTokenExpiry = timezone.now() + timedelta(hours=1)
            subject = "Reset your password"
        else:
            raise ValueError("Invalid email_type. Must be 'VERIFY' or 'RESET'.")

        user.save()


        domain = "http://localhost:3000" 
        link_path = "verifyemail"  # Adjust if your URL route is something else

        html_content = f"""
        <p>
            Click <a href="{domain}/{link_path}?token={hashed_token}">here</a> to 
            {"verify your email" if email_type == "VERIFY" else "reset your password"}.<br><br>
            Or copy and paste this link in your browser:<br>
            {domain}/{link_path}?token={hashed_token}
        </p>
        """

        # 4) Send the email with Django's send_mail
        send_mail(
            subject=subject,
            message="Please use an HTML-capable client to view this message.",  # Fallback text
            from_email="hitesh@gmail.com",
            recipient_list=[email],
            html_message=html_content,  # Our HTML body
            fail_silently=False,
        )

        return True

    except Exception as e:
        # You can log or raise an error here
        raise e
    
@api_view(["POST"])
def signup(request):
    print("signup is called")
    # Extract validated data
    data = request.data
    email = data["email"]
    username = data["name"]
    password = data["password"]
    curr_time = data["curr_date"]

    # 2. Check if the email already exists
    if SoundscapeUser.objects.filter(email=email).exists():
        return Response(
            {"error": "Email already exists, please use a different email or login."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 3. Hash the password
    hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    # 4. Insert user into the database
    user = SoundscapeUser.objects.create(
        username=username, password=hashed_password, email=email, timestamp=curr_time
    )

    print("Inserted user:", user)

    if not user:
        return Response(
            {"error": "An error occurred while creating your account."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # 5. Generate JWT Token and Set-Cookie
    token, expires_at = generate_jwt_token(user)

    response = Response(
        {
            "message": "Signup successful. Please check your inbox for email verification",
        },
        status=status.HTTP_201_CREATED,
    )

    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=True,
        samesite="Lax",
        expires=expires_at,
    )
    send_email(email, "VERIFY", user.user_id)

    return response


@api_view(["POST"])
def logout(request):
    """
    Log the user out by removing the 'session' cookie.
    """
    response = Response({"message": "Logout successful"}, status=status.HTTP_200_OK)
    # Either delete the cookie:
    response.delete_cookie("session")

    # Alternatively, you could set it to expire immediately:
    # response.set_cookie(
    #     key="session",
    #     value="",
    #     expires=0,  # Expires now
    #     httponly=True,
    #     secure=True,
    #     samesite="Lax",
    # )

    return response


@api_view(["GET"])
def get_name(request):
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
    userid = session_payload.userid
    User = SoundscapeUser.objects.get(user_id=userid)
    return Response(
        {"name": User.username},
        status=status.HTTP_200_OK,
    )



@api_view(["POST"])
def google_auth(request):
    id_token_from_client = request.data.get("id_token")
    if not id_token_from_client:
        return Response(
            {"error": "No ID token provided."}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Verify the token using your Google Client ID
        id_info = google_id_token.verify_oauth2_token(
            id_token_from_client,
            google_requests.Request(),
            os.getenv("GOOGLE_CLIENT_ID"),
        )
        # Google's unique user ID
        google_user_id = id_info.get("sub")
        email = id_info.get("email")
        name = id_info.get("name")
    except ValueError as e:
        return Response(
            {"error": "Invalid ID token.", "details": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Try to find an existing user by google_user_id or email
    try:
        user = SoundscapeUser.objects.get(google_user_id=google_user_id)
    except SoundscapeUser.DoesNotExist:
        # Optionally, check if there's a non-Google account with the same email
        try:
            user = SoundscapeUser.objects.get(email=email)
            # Link the account by setting google_user_id
            user.google_user_id = google_user_id
            user.save()
        except SoundscapeUser.DoesNotExist:
            # Create a new user if no account exists
            user = SoundscapeUser.objects.create(
                google_user_id=google_user_id,
                username=name,
                email=email,
                password=None,
            )

    token, expires_at = generate_jwt_token(user)
    response = Response({"message": "Authenticated"}, status=status.HTTP_200_OK)
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=True,
        samesite="Lax",
        expires=expires_at,
    )
    return response

@api_view(["GET"])
def get_all_users(request):
    """Fetch all users from the database."""
    users = SoundscapeUser.objects.filter(profile_id__isnull=False)
    serializer = SoundscapeUserSerializer(users, many=True)
    return Response(serializer.data)

@api_view(["GET"])
def search_users(request):
    """Search users by display name."""
    query = request.query_params.get("query", "")

    if not query:
        return Response({"error": "Query parameter is required."}, status=400)

    matching_users = SoundscapeUser.objects.filter(username__icontains=query, profile_id__isnull=False)
    serializer = SoundscapeUserSerializer(matching_users, many=True)
    
    return Response(serializer.data)


@api_view(["POST"])
def verify_email(request):
    try:
        data = request.data
        token = data.get('token')
        now = timezone.now()

        # Try email verification token
        user = SoundscapeUser.objects.filter(verifyToken=token).first()
        if user:
            # Check if the token has expired
            if user.verifyTokenExpiry is None or user.verifyTokenExpiry < now:
                return Response({
                    'error': 'Verification token expired. Please request a new verification email.'
                }, status=400)

            # Mark the user as verified and clear token data
            user.isVerified = True  
            user.verifyToken = None
            user.verifyTokenExpiry = None
            user.save()
            return Response({
                'message': 'Email verified successfully. You can now close this page.',
                'success': True
            })

        # Check for forgot password token
        user = SoundscapeUser.objects.filter(forgotPasswordToken=token).first()
        if user:
            # Check if the forgot password token has expired
            if user.forgotPasswordTokenExpiry is None or user.forgotPasswordTokenExpiry < now:
                return Response({
                    'error': 'Reset token expired. Please request a new password reset link.'
                }, status=400)
            
            return Response({
                'message': 'Reset token detected. Redirect to reset password page if needed.',
                'success': True,
                'action': 'reset'
            })

        return Response({'error': 'Invalid token'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=500)



@api_view(["POST"])
def request_password_reset(request):
    data = request.data
    email = data.get("email")
    if not email:
        return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = SoundscapeUser.objects.get(email=email)
    except SoundscapeUser.DoesNotExist:
        # Optionally, you might not want to reveal whether an email exists
        return Response({"error": "User does not exist."}, status=status.HTTP_404_NOT_FOUND)

    try:
        # This will update the user's forgotPasswordToken and expiry, then send the email.
        send_email(email, "RESET", user.user_id)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"message": "Password reset email sent."}, status=status.HTTP_200_OK)


@api_view(["POST"])
def reset_password(request):
    data = request.data
    token = data.get("token")
    new_password = data.get("new_password")
    
    if not token or not new_password:
        return Response(
            {"error": "Both token and new password are required."}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Query for a user with a matching reset token
    user = SoundscapeUser.objects.filter(forgotPasswordToken=token).first()
    
    if not user:
        return Response(
            {"error": "Invalid token."}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if the token has expired
    if user.forgotPasswordTokenExpiry is None or user.forgotPasswordTokenExpiry < timezone.now():
        return Response(
            {"error": "Token expired. Please request a new password reset."}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        hashed_password = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        user.password = hashed_password

        # Clear the reset token and expiry
        user.forgotPasswordToken = None
        user.forgotPasswordTokenExpiry = None
        user.save()
    except Exception as e:
        return Response(
            {"error": str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    return Response(
        {"message": "Password reset successfully."}, 
        status=status.HTTP_200_OK
    )


'''
making friends 
'''
def get_current_user(request):
    session_cookie = request.COOKIES.get("session")
    if not session_cookie:
        return None, Response(
            {"error": "No session token provided."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    
    session_payload = decrypt_session_token(session_cookie)
    if not session_payload or not session_payload.userid:
        return None, Response(
            {"error": "Invalid or expired session."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    try:
        user = User.objects.get(spotify_id=session_payload.spotify_id)
    except User.DoesNotExist:
        return None, Response(
            {"error": "User not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return user, None


@api_view(["POST"])
def send_friend_request(request):
    """
    Send a friend request from the current user (sender) to a receiver.
    Expects JSON payload: {"receiver_id": <receiver_user_spotify_id>}
    """
    current_user, error_response = get_current_user(request)
    if error_response:
        return error_response

    receiver_id = request.data.get("receiver_id")
    print(receiver_id)
    if not receiver_id:
        return Response(
            {"error": "Receiver ID is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Prevent sending a friend request to oneself.
    if current_user.spotify_id == receiver_id:
        return Response(
            {"error": "You cannot send a friend request to yourself."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    receiver = get_object_or_404(User, spotify_id=receiver_id)

    # 2. Check if they are already friends
    #    If your Friendship model has user1, user2 fields for each friendship:
    if Friendship.objects.filter(
        Q(user1=current_user, user2=receiver) | Q(user1=receiver, user2=current_user)
    ).exists():
        return Response(
            {"error": "You are already friends with this user."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 3. Check for existing friend requests from current_user to receiver
    #    We only block a new request if there's an existing "pending" or "accepted" request
    #    Because "accepted" means they're friends (already caught above), but in case you
    #    store an 'accepted' request and not a Friendship record, we handle that scenario too.
    existing_request = FriendRequest.objects.filter(sender=current_user, receiver=receiver).order_by('-created_at').first()
    if existing_request:
        if existing_request.status in ["pending", "accepted"]:
            return Response(
                {"error": "A friend request to this user already exists or has been accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else: 
            # If the request exists but is 'rejected' or 'cancelled', we can delete it and proceed
            existing_request.delete()
    

    friend_request = FriendRequest.objects.create(
        sender=current_user,
        receiver=receiver
    )
    return Response(
        {"message": "Friend request sent.", "friend_request_id": friend_request.id},
        status=status.HTTP_201_CREATED,
    )

@api_view(["POST"])
def accept_friend_request(request, request_id):
    """
    Accept a friend request.
    The current user must be the receiver of the friend request.
    """
    current_user, error_response = get_current_user(request)
    if error_response:
        return error_response

    friend_request = get_object_or_404(FriendRequest, id=request_id)

    # Only the receiver can accept the friend request.
    if current_user != friend_request.receiver:
        return Response(
            {"error": "You are not authorized to accept this friend request."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if friend_request.status != "pending":
        return Response(
            {"error": "This friend request is not pending."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    friend_request.status = "accepted"
    friend_request.save()

    user1, user2 = sorted(
        [friend_request.receiver, friend_request.sender],
        key=lambda user: user.spotify_id
    )
    # Use get_or_create to avoid duplicates in case the friendship already exists.
    Friendship.objects.get_or_create(user1=user1, user2=user2)


    return Response(
        {"message": "Friend request accepted and friendship created."},
        status=status.HTTP_200_OK,
    )

@api_view(["POST"])
def reject_friend_request(request, request_id):
    """
    Reject a friend request.
    The current user must be the receiver.
    """
    current_user, error_response = get_current_user(request)
    if error_response:
        return error_response

    friend_request = get_object_or_404(FriendRequest, id=request_id)

    if current_user != friend_request.receiver:
        return Response(
            {"error": "You are not authorized to reject this friend request."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if friend_request.status != "pending":
        return Response(
            {"error": "This friend request is not pending."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    friend_request.status = "rejected"
    friend_request.save()

    return Response(
        {"message": "Friend request rejected."},
        status=status.HTTP_200_OK,
    )

@api_view(["POST"])
def cancel_friend_request(request, request_id):
    """
    Cancel a friend request.
    Only the sender can cancel a pending friend request.
    """
    current_user, error_response = get_current_user(request)
    if error_response:
        return error_response

    friend_request = get_object_or_404(FriendRequest, id=request_id)

    if current_user != friend_request.sender:
        return Response(
            {"error": "You are not authorized to cancel this friend request."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if friend_request.status != "pending":
        return Response(
            {"error": "Only pending friend requests can be cancelled."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    friend_request.status = "cancelled"
    friend_request.save()

    return Response(
        {"message": "Friend request cancelled."},
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
def incoming_friend_requests(request):
    """
    List incoming (received) pending friend requests for the current user.
    """
    current_user, error_response = get_current_user(request)
    if error_response:
        return error_response

    friend_requests = FriendRequest.objects.filter(receiver=current_user, status="pending")
    data = [
        {
            "id": fr.id,
            "sender_id": fr.sender.spotify_id,
            "sender_display_name": fr.sender.display_name,
            "created_at": fr.created_at,
        }
        for fr in friend_requests
    ]
    return Response(data, status=status.HTTP_200_OK)

@api_view(["GET"])
def outgoing_friend_requests(request):
    """
    List outgoing (sent) pending friend requests for the current user.
    """
    current_user, error_response = get_current_user(request)
    if error_response:
        return error_response

    friend_requests = FriendRequest.objects.filter(sender=current_user, status="pending")
    data = [
        {
            "id": fr.id,
            "receiver_id": fr.receiver.spotify_id,
            "receiver_display_name": fr.receiver.display_name,
            "created_at": fr.created_at,
        }
        for fr in friend_requests
    ]
    return Response(data, status=status.HTTP_200_OK)

@api_view(["GET"])
def friends(request):
    """
    List friends of the current user.
    """
    current_user, error_response = get_current_user(request)
    if error_response:
        return error_response

    friends = Friendship.objects.filter(Q(user1=current_user) | Q(user2=current_user))
    data = []
    for friendship in friends:
        friend = friendship.user1 if friendship.user1 != current_user else friendship.user2
        # Get the associated SoundscapeUser through the profile relationship
        soundscape_user = SoundscapeUser.objects.filter(profile=friend).first()
        if soundscape_user:
            data.append({
                "id": friend.spotify_id,
                "display_name": friend.display_name,
                "soundscape_id": str(soundscape_user.user_id)  
            })
    return Response(data, status=status.HTTP_200_OK)

''' 
monthly 5 genre
'''
@api_view(["GET"])
def monthly_top5_genres(request):
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
    #userid = session_payload.userid
    spotify_id = session_payload.spotify_id  # Hardcoded for demonstration

    # Aggregate listen_count per month and genre, including genre name
    qs = (
        UserGenreListening.objects
        .filter(user_id=spotify_id)
        .annotate(month=TruncMonth('time_collected'))
        .values('month', 'genre_id', 'genre__name')  # <--- Include genre__name
        .annotate(total_listens=Sum('listen_count'))
        .order_by('month', '-total_listens')
    )
    print(qs)

    # Group the data by month
    monthly_data = defaultdict(list)
    for record in qs:
        monthly_data[record['month']].append({
            'genre_id': record['genre_id'],
            'genre_name': record['genre__name'],   # <--- Now we have the name
            'total_listens': record['total_listens']
        })

    # For each month, select the top 5 genres and format the month as a string
    result = []
    for month, records in monthly_data.items():
        top5 = records[:5]  # because qs is already ordered descending by total_listens per month
        result.append({
            'month': month.strftime('%Y-%m'),
            'top5_genres': top5
        })

    return JsonResponse(result, safe=False)


"""
Going to concert feature
"""
def require_auth(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
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

        try:
            request.user = SoundscapeUser.objects.get(user_id=session_payload.userid)
        except ObjectDoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return view_func(request, *args, **kwargs)
    return wrapper


@api_view(['POST'])
@require_auth
def toggle_concert_attendance(request):
    concert_id = request.data.get('concert_id')
    if not concert_id:
        return Response(
            {'error': 'concert_id is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    user = request.user  # This is now your SoundscapeUser instance
    
    # If user is already attending, remove attendance
    if user.is_attending_concert(concert_id):
        user.unattend_concert(concert_id)
        return Response({'status': 'unattended'})
    
    # If not attending, add attendance
    user.attend_concert(concert_id)
    return Response({'status': 'attending'})

@api_view(['GET'])
def get_concert_attendees(request, concert_id):
    """Get all users attending a specific concert"""
    attendees = SoundscapeUser.objects.filter(
        concert_attendances__concert_id=concert_id
    )
    attendees_data = [
        {
            'user_id': str(attendee.user_id),
            'username': attendee.username,
            'pfp': attendee.pfp
        }
        for attendee in attendees
    ]
    return Response(attendees_data)

@api_view(['GET'])
@require_auth
def get_user_attending_concerts(request):
    """Get all concerts the current user is attending"""
    user = request.user  # This is now your SoundscapeUser instance
    concert_ids = user.get_attending_concerts()
    return Response({'attending_concerts': list(concert_ids)})


@api_view(['POST'])
@require_auth
def invite_friend_to_concert(request):
    friend_id = request.data.get('friend_id')
    concert_id = request.data.get('concert_id')
    concert_name = request.data.get('concert_name')
    event_url = request.data.get('event_url')
    
    if not all([friend_id, concert_id, concert_name]):
        return Response(
            {'error': 'Missing required fields'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        friend = SoundscapeUser.objects.get(user_id=friend_id)
        
        # Check if invitation already exists
        existing_invite = Notification.objects.filter(
            recipient=friend,
            sender=request.user,
            notification_type='concert_invite',
            concert_id=concert_id,
            event_url=event_url
        ).exists()
        
        if existing_invite:
            return Response(
                {'error': 'Invitation already sent'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Create notification
        notification = Notification.objects.create(
            recipient=friend,
            sender=request.user,
            notification_type='concert_invite',
            concert_id=concert_id,
            concert_name=concert_name,
            event_url=event_url
        )

        # Send real-time notification via WebSocket
        channel_layer = get_channel_layer()
        notification_data = {
            'id': notification.id,
            'type': notification.notification_type,
            'sender': {
                'user_id': str(notification.sender.user_id),
                'username': notification.sender.username,                
                'pfp': notification.sender.pfp
            },
            'concert_id': notification.concert_id,
            'concert_name': notification.concert_name,
            'event_url': notification.event_url,
            'created_at': notification.created_at.isoformat(),
            'is_read': notification.is_read
        }
        
        async_to_sync(channel_layer.group_send)(
            f"notifications_{friend.user_id}",
            {
                "type": "notification_message",
                "data": notification_data
            }
        )
        
        return Response(
            {'message': 'Invitation sent successfully'},
            status=status.HTTP_200_OK
        )
        
    except SoundscapeUser.DoesNotExist:
        return Response(
            {'error': 'User not found'},
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['GET'])
@require_auth
def get_notifications(request):
    notifications = Notification.objects.filter(recipient=request.user)
    
    notifications_data = [{
        'id': notif.id,
        'type': notif.notification_type,
        'sender': {
            'user_id': notif.sender.user_id,
            'username': notif.sender.username,
            'pfp': notif.sender.profile_picture_url if hasattr(notif.sender, 'profile_picture_url') else None
        },
        'concert_id': notif.concert_id,
        'concert_name': notif.concert_name,
        'created_at': notif.created_at,
        'is_read': notif.is_read
    } for notif in notifications]
    
    return Response({
        'notifications': notifications_data
    })

@api_view(['POST'])
@require_auth
def mark_notification_read(request):
    notification_id = request.data.get('notification_id')
    
    try:
        notification = Notification.objects.get(
            id=notification_id,
            recipient=request.user
        )
        notification.is_read = True
        notification.save()
        return Response({'status': 'success'})
    except Notification.DoesNotExist:
        return Response(
            {'error': 'Notification not found'},
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['DELETE'])
@require_auth
def delete_notification(request, notification_id):
    try:
        notification = Notification.objects.get(
            id=notification_id,
            recipient=request.user
        )
        notification.delete()
        return Response({'status': 'success'})
    except Notification.DoesNotExist:
        return Response(
            {'error': 'Notification not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@require_auth
def get_chats(request):
    """Get all chats for the current user"""
    chats = Chat.objects.filter(participants=request.user)
    
    chats_data = []
    for chat in chats:
        # Get the other participant
        other_participant = chat.participants.exclude(user_id=request.user.user_id).first()
        if not other_participant:
            continue
            
        # Get the last message
        last_message = chat.messages.order_by('-created_at').first()
        
        chats_data.append({
            'id': chat.id,
            'participant': {
                'user_id': str(other_participant.user_id),
                'username': other_participant.username,
                'pfp': other_participant.pfp
            },
            'last_message': {
                'content': last_message.content if last_message else None,
                'created_at': last_message.created_at.isoformat() if last_message else None,
                'sender_id': str(last_message.sender.user_id) if last_message else None
            },
            'updated_at': chat.updated_at.isoformat()
        })
    
    return Response({'chats': chats_data})

@api_view(['GET'])
@require_auth
def get_chat_messages(request, chat_id):
    """Get all messages for a specific chat"""
    try:
        chat = Chat.objects.get(id=chat_id, participants=request.user)
        messages = chat.messages.all()
        
        messages_data = [{
            'id': message.id,
            'content': message.content,
            'sender': {
                'user_id': str(message.sender.user_id),
                'username': message.sender.username,
                'pfp': message.sender.pfp
            },
            'created_at': message.created_at.isoformat(),
            'is_read': message.is_read
        } for message in messages]
        
        return Response({'messages': messages_data})
    except Chat.DoesNotExist:
        return Response(
            {'error': 'Chat not found'},
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['POST'])
@require_auth
def create_chat(request):
    """Create a new chat with another user"""
    participant_id = request.data.get('participant_id')
    
    if not participant_id:
        return Response(
            {'error': 'Participant ID is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        participant = SoundscapeUser.objects.get(user_id=participant_id)
        
        # Check if chat already exists
        existing_chat = Chat.objects.filter(
            participants=request.user
        ).filter(
            participants=participant
        ).first()
        
        if existing_chat:
            return Response({
                'chat_id': existing_chat.id,
                'message': 'Chat already exists'
            })
        
        # Create new chat
        chat = Chat.objects.create()
        chat.participants.add(request.user, participant)
        
        return Response({
            'chat_id': chat.id,
            'message': 'Chat created successfully'
        })
        
    except SoundscapeUser.DoesNotExist:
        return Response(
            {'error': 'User not found'},
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['POST'])
@require_auth
def mark_messages_read(request, chat_id):
    """Mark all messages in a chat as read"""
    try:
        chat = Chat.objects.get(id=chat_id, participants=request.user)
        chat.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
        return Response({'status': 'success'})
    except Chat.DoesNotExist:
        return Response(
            {'error': 'Chat not found'},
            status=status.HTTP_404_NOT_FOUND
        )

def verify_session(request):
    session_cookie = request.COOKIES.get("session")
    if not session_cookie:
        return Response(
            {'error': 'Session cookie not found'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    try:
        session_payload = decrypt_session_token(session_cookie)
        if not session_payload:
            return Response(
                {'error': 'Invalid session cookie'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        return session_payload
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_401_UNAUTHORIZED
        )