import tekore as tk
import os
from rest_framework.response import Response
from rest_framework import status

from dotenv import load_dotenv
from django.db import transaction
from django.utils.dateparse import parse_datetime
from tqdm import tqdm
from django.core.exceptions import ObjectDoesNotExist
from MySQLdb import OperationalError  # or: from django.db.utils import OperationalError
from collections import Counter
from django.utils import timezone


import logging
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "soundscape.settings")

logger = logging.getLogger(__name__)
import django

django.setup()

from music.services import save_or_update_track, get_or_create_artist
from users.models import User, UserTopTrack, UserTopArtist, UserGenreListening, Genre
from music.services import import_user_playlists


load_dotenv()
client_id = os.getenv("spotify_client_id")
client_secret = os.getenv("spotify_client_secret")
redirect_uri = os.getenv("spotify_redirect_uri")
cred = tk.RefreshingCredentials(client_id, client_secret, redirect_uri)


def _update_user_access_token(spotify_id, access_token):
    """
    Updates the access and refresh token for a user with the given Spotify ID.

    Parameters:
    spotify_id (str): The Spotify ID of the user.
    refreshing_token (tk.RefreshingToken): The new token object containing updated access and refresh tokens.
    """
    try:

        # Retrieve the user with the given Spotify ID
        user = User.objects.get(spotify_id=spotify_id)

        # Update the access token
        user.access_token = access_token

        # Save the changes to the database
        user.save()
        logger.info(f"Access token updated successfully for user {spotify_id}.")
    except ObjectDoesNotExist:
        logger.error(f"User with Spotify ID {spotify_id} does not exist.")
    except ValueError as ve:
        logger.error(f"ValueError while updating user token: {ve}")
    except Exception as e:
        logger.exception(
            f"Unexpected error occurred while updating access token for {spotify_id}: {e}"
        )


def error_handling_spotify_authentication(error, user, access_token, refresh_token, spotify_id):
    if error.response.status_code == 401:  # Unauthorized, token might be expired
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
        print(f"Error using access token: {error}")
        return Response(
            {"error": f"Error using access token: {error}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Ensure user exists in our database
    # user, _ = User.objects.get_or_create(spotify_id=spotify_id)
    # return spotify, user


def get_user_recently_listened(spotify_id):
    """
    Fetch recently played tracks for a user, update or save them in the database,
    and mark them as recently listened.
    """
    try:
        # Get the current user and their access token
        cur_user = User.objects.get(spotify_id=spotify_id)
        token = cur_user.access_token
        refresh_token = cur_user.refresh_token
        sp = tk.Spotify(token)

        # Fetch recently played tracks



        recently_played = sp.playback_recently_played(limit=50).model_dump()

        # Process each recently played track
        print(len(recently_played["items"]))
        for item in recently_played["items"]:
            track_data = item["track"]
            print('GPTTTTT')
            if not track_data:
                continue  # Skip if no track data

            # Save or update the track in the database
            try: 
                track_obj = save_or_update_track(track_data)
            except Exception as e:
                print(f"save update track failed: {e}")
                continue      
            # Update the UserTopTrack entry for the user and track
            if track_obj:
                try: 
                    user_top_track, _ = UserTopTrack.objects.update_or_create(
                        user=cur_user,
                        track=track_obj[0],
                        time_range="short_term",  # Assume short_term for recently listened
                        defaults={
                            "recently_listened": True,
                            # only applicable for recently listened tracks,
                            "played_at": item["played_at"],
                        },
                        rank=-1,
                    )
                except Exception as e:
                    print(f"Transaction failed: {e}")
                    continue
    except tk.HTTPError as e:
        error_handling_spotify_authentication(e, cur_user, token, refresh_token, spotify_id)
    except User.DoesNotExist:
        print(f"User with Spotify ID {spotify_id} does not exist.")
    except Exception as e:
        print(f"An error occurred: {e}")


def get_sp(user_id):
    cur_user = User.objects.get(spotify_id=user_id)
    sp = tk.Spotify(cur_user.access_token)
    return cur_user, sp


def fetch_and_save_user_top_tracks(user, sp, time_range="short_term", fetch_all=False):
    """
    Fetch and save the user's top tracks from Spotify.

    Args:
        user: The user for whom to fetch the top tracks.
        sp: The Spotify API client instance.
        time_range: The time range for the top tracks (e.g., 'short_term', 'medium_term', 'long_term').
        fetch_all: Whether to fetch all pages of results (default: False).

    Returns:
        None
    """
    all_tracks = []
    initial_page = sp.current_user_top_tracks(time_range=time_range, limit=10)
    all_tracks.extend(initial_page.items)


    print('popery popery popery')

    if fetch_all:
        # Fetch all pages of results
        while initial_page.next:
            initial_page = sp.next(initial_page)
            all_tracks.extend(initial_page.items)

    # Save tracks and user top track rankings
    for rank, track in tqdm(
        enumerate(all_tracks, start=1),
        total=len(all_tracks),
        desc=f"Saving top tracks for user {user.display_name} ({time_range})",
        unit="track",
    ):
        try: 
            track_obj = save_or_update_track(track.dict())
        except django.db.utils.OperationalError as e:
            if "SAVEPOINT" in str(e):
                print('vilent johnson 2020')
                continue
            else:
                raise 
        # Save user top track
        # print(user)
        # print(track)
        try:
            UserTopTrack.objects.update_or_create(
                user=user,
                track=track_obj[0],
                time_range=time_range,
                defaults={"rank": rank},
            )
        except django.db.utils.OperationalError as e:
            if "SAVEPOINT" in str(e):
                print('vilent johnson')
                continue
            else:
                raise

        print('tin do od o tin')


def fetch_and_save_user_top_artists(user, sp, time_range="short_term", fetch_all=False):
    """
    Fetch and save the user's top artists from Spotify.

    Args:
        user: The user for whom to fetch the top artists.
        sp: The Spotify API client instance.
        time_range: The time range for the top artists (e.g., 'short_term', 'medium_term', 'long_term').
        fetch_all: Whether to fetch all pages of results (default: False).

    Returns:
        None
    """
    all_artists = []
    initial_page = sp.current_user_top_artists(limit=50, time_range=time_range)
    all_artists.extend(initial_page.items)

    if fetch_all:
        # Fetch all pages of results
        while initial_page.next:
            initial_page = sp.next(initial_page)
            all_artists.extend(initial_page.items)

    # Iterate through the artists and save them to the database
    for rank, artist in tqdm(
        enumerate(all_artists, start=1),
        total=len(all_artists),
        desc=f"Saving top artists for user {user.display_name} ({time_range})",
        unit="artist",
    ):
        # Create or retrieve the artist object
        try:
            artist_obj = get_or_create_artist(artist.model_dump())
        except django.db.utils.OperationalError as e:
            # If the error message contains "SAVEPOINT", skip this artist and continue
            if "SAVEPOINT" in str(e):
                print('violent')
                continue
            else:
                raise     
        # Save user top artist
        try:
            obj = UserTopArtist.objects.get(user=user, artist=artist_obj, time_range=time_range)
            # Update the record
            obj.rank = rank
            obj.save()
        except django.db.utils.OperationalError as e:
            # If the error message contains "SAVEPOINT", skip this artist and continue
            if "SAVEPOINT" in str(e):
                print('violent')
                continue
            else:
                raise     
        except UserTopArtist.DoesNotExist:

            try: 
                # Create the record
                obj = UserTopArtist.objects.create(
                    user=user,
                    artist=artist_obj,
                    time_range=time_range,
                    rank=rank,
                )
            except django.db.utils.OperationalError as e:
                # If the error message contains "SAVEPOINT", skip this artist and continue
                if "SAVEPOINT" in str(e):
                    print('violent')
                    continue
                else:
                    raise
        # UserTopArtist.objects.update_or_create(
        #     user=user,
        #     artist=artist_obj,
        #     time_range=time_range,
        #     defaults={"rank": rank},
        # )

def fetch_and_store_top_genres(user):
    """
    Fetches top genres from Spotify for a user and stores them in the database.
    """
    try:
        token = user.access_token
        if not token:
            print(f"No access token found for user {user.spotify_id}")
            return
        
        sp = tk.Spotify(token)
        
        for time_range in ["short_term", "medium_term", "long_term"]:
            print(f"Fetching top artists for {user.spotify_id} ({time_range})")

            # Fetch top artists
            top_artists = sp.current_user_top_artists(time_range=time_range, limit=50)
            
            # Count genres
            genre_counts = Counter()
            for artist in top_artists.items:
                for genre in artist.genres:
                    genre_counts[genre] += 1

            # Store in DB
            for genre_name, count in genre_counts.items():
                # print("genre", genre_name, "count", count)
                # Get or create the Genre object for the given genre name
                genre_obj, created = Genre.objects.get_or_create(name=genre_name)
                try: 
                  UserGenreListening.objects.update_or_create(
                      user=user,
                      genre=genre_obj,
                      time_range=time_range,  # make sure time_range is a valid field for UserGenreListening
                      time_collected=timezone.now(),
                      defaults={"listen_count": count}
                  )
                except django.db.utils.OperationalError as e:
                    # If the error message contains "SAVEPOINT", skip this artist and continue
                    if "SAVEPOINT" in str(e):
                        print('viola')
                        continue
                    else:
                        raise

            print(f"Stored {len(genre_counts)} genres for {user.spotify_id} ({time_range})")
    
    except tk.HTTPError as e:
        print(f"Error fetching top genres: {str(e)}")

def check_if_current_user_follows(spotify_id, user_ids: list[str]) -> list[bool]:
    """
    Check if the user with spotify_id follows each user in user_ids.
    Returns a list of booleans in the same order as user_ids.
    """
    print(f"Checking if user {spotify_id} follows users: {user_ids}")

    try:
        cur_user = User.objects.get(spotify_id=spotify_id)
        token = cur_user.access_token
        refresh_token = cur_user.refresh_token
    except User.DoesNotExist:
        raise ValueError(f"No local user found with spotify_id={spotify_id}")

    try:
        sp = tk.Spotify(token)
        return sp.users_is_following(user_ids)
    except tk.Forbidden as e:
        if "Insufficient client scope" in str(e):
            print("Token missing scope, refreshing...")

            try:
                new_token = cred.refresh_user_token(refresh_token)
                sp = tk.Spotify(new_token.access_token)

                # Handle missing expires_in
                expires_in = new_token.expires_in if new_token.expires_in is not None else 3600  # Default to 1 hour
                print(f"New token expires in: {expires_in} seconds")

                # Update user's access token in the database
                cur_user.access_token = new_token.access_token
                cur_user.token_expires = timezone.now() + timedelta(seconds=expires_in)
                cur_user.save()

                return sp.users_is_following(user_ids)

            except tk.HTTPError as refresh_error:
                print(f"Failed to refresh token: {refresh_error}")
                raise ValueError("User needs to re-authenticate with proper scopes.")

        else:
            raise e

def main():
    # NOTE: to be run async when a new user joined
    user_id = "falbert88"
    user, sp = get_sp(user_id)
    get_user_recently_listened(user_id)
    import_user_playlists(user_id)
    fetch_and_save_user_top_tracks(user, sp, fetch_all=True)
    fetch_and_save_user_top_artists(user, sp, fetch_all=True)


if __name__ == "__main__":
    main()
