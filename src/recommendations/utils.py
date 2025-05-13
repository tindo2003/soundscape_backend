import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
from dotenv import load_dotenv


def get_spotipy_client(client_id=None, client_secret=None):
    """Get the spotipy client to access the Spotify API with.

    Args:
        client_id (str): The client id to connect to the Spotify API with.
        client_secret (str): The client secret to connect to the Spotify API with.

    Returns:
        A spotipy client.
    """
    if client_id is None and client_secret is None:
        # load credentials from the .env file
        assert load_dotenv(), "no enviromental variables found!"
        client_id = os.environ["SPOTIFY_CLIENT_ID"]
        client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]

    # create spotify obj
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=client_id,
        client_secret=client_secret
    ))
    return sp


def get_info(uri, uri_type, client_id=None, client_secret=None):
    """Extracts information about Spotify track(s)/artist(s)/album(s)
    given its(their) URI(s).
    Maximum of 50 URIs could be handled at the same time.

    Args:
        uri(str/list): The Spotify track/artist/album URI(s)
        uri_type(str): The type of URI, either "track", "artist", or "album"
        client_id (str): The client id to connect to the Spotify API with.
        client_secret (str): The client secret to connect to the Spotify API with.

    Returns:
        dict/list: A (list of) dictionary with the track/artist/album info,
                   or None if an error occurs.
    """
    acceptable_types = ("track", "artist", "album")
    assert isinstance(uri, (list, str))
    assert isinstance(uri_type, str) and uri_type in acceptable_types

    sp = get_spotipy_client(client_id, client_secret)

    # generate fetch func
    fetch_funcs = (sp.track, sp.artist, sp.album)
    if isinstance(uri, list):
        fetch_funcs = (sp.tracks, sp.artists, sp.albums)
    fetch_func = fetch_funcs[acceptable_types.index(uri_type)]

    try:
        # Attempt to fetch information, handling potential exceptions
        info = fetch_func(uri)
        if isinstance(uri, list):
            info = info[uri_type + "s"]
        return info

    except spotipy.exceptions.SpotifyException as e:
        print(f"Error fetching track info: {e}")
        return None


if __name__ == "__main__":
    # sample usages
    track_uri = "spotify:track:0UaMYEvWZi0ZqiDOoHU3YI"
    track_info = get_info(track_uri, "track")
    print(track_info, '\n')

    artist_uri = "spotify:artist:2wIVse2owClT7go1WT98tk"
    artist_info = get_info(artist_uri, "artist")
    print(artist_info, '\n')

    album_uri = "spotify:album:6vV5UrXcfyQD1wu4Qo2I9K"
    album_info = get_info(album_uri, "album")
    print(album_info, '\n')

    tracks_uri = ["spotify:track:0UaMYEvWZi0ZqiDOoHU3YI",
                  "spotify:track:6I9VzXrHxO9rA9A5euc8Ak"]
    tracks_info = get_info(tracks_uri, "track")
    print(tracks_info, '\n')
