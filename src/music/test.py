from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
import os
from dotenv import load_dotenv
from django.db import transaction

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "soundscape.settings")

import django

django.setup()
from users.models import User
from music.models import Playlist, Artist, Album, Track, Genre
from tqdm import tqdm

load_dotenv()


def get_playlist_tracks_by_popularity(playlist_name):
    """
    Fetch all tracks for a given playlist name, ranked by popularity.
    """
    try:
        # Retrieve the playlist object by name
        playlist = Playlist.objects.get(name=playlist_name)

        # Query all tracks related to the playlist, ordered by popularity
        tracks = playlist.tracks.all().order_by("-popularity")

        # Print or process the results
        for track in tracks[:10]:
            print(
                f"Track ID: {track.track_id}, Name: {track.name}, Popularity: {track.popularity}"
            )

        return tracks
    except Playlist.DoesNotExist:
        print(f"Playlist named '{playlist_name}' does not exist.")
        return None


def main():
    get_playlist_tracks_by_popularity("Complete Works: Tchaikovsky")


# Example usage
if __name__ == "__main__":
    main()
