from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
import os
from dotenv import load_dotenv
from django.db import transaction
import tekore as tk

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "soundscape.settings")

import django

django.setup()
from users.models import User
from music.models import Playlist, Artist, Album, Track, Genre
from tqdm import tqdm

load_dotenv()


def import_user_playlists(spotify_id: str):
    #Playlist.objects.all().delete()
    scope = "playlist-read-private"  # Required scope for playback_recently_played
    cur_user = User.objects.get(spotify_id=spotify_id)
    sp = Spotify(auth=cur_user.access_token)

    playlists = sp.user_playlists(spotify_id)
    while playlists:
        for i, playlist_data in enumerate(playlists["items"]):
            playlist_id = playlist_data.get("id")
            playlist_name = playlist_data.get("name", "")
            collaborative = playlist_data.get("collaborative", False)
            public = playlist_data.get("public", True)
            description = playlist_data.get("description", "")
            uri = playlist_data.get("uri", "")
            owner = playlist_data.get("owner", {})
            owner_id = owner.get("id", "")
            external_urls = playlist_data.get("external_urls", {})
            external_url_spotify = external_urls.get("spotify", "")

            playlist_obj, _created = Playlist.objects.get_or_create(
                playlist_id=playlist_id,
                defaults={
                    "name": playlist_name,
                    "owner_id": owner_id,
                    "collaborative": collaborative,
                    "public": public,
                    "description": description,
                    "uri": uri,
                    "external_url": external_url_spotify,
                },
            )
            if not _created:
                print(f"Playlist '{playlist_name}' already exists. Skipping...")
                continue

            # -----------------------
            # 3. Retrieve all tracks for this playlist
            # -----------------------
            all_tracks_in_playlist = _fetch_all_playlist_items(sp, playlist_id)

            # -----------------------
            # 4. Save (or update) each track and link it to the playlist
            # -----------------------
            _save_and_link_tracks(
                container_obj=playlist_obj,
                track_items=all_tracks_in_playlist,
                track_extractor=lambda item: item.get(
                    "track"
                ),  # playlist item has a "track" key
            )
        if playlists["next"]:
            playlists = sp.next(playlists)
        else:
            playlists = None


def _save_and_link_tracks(container_obj, track_items, track_extractor):
    """
    Given:
        - a container_obj that has a ManyToMany 'tracks' (e.g. a Playlist or an Album),
        - a list of 'track_items' from Spotify,
        - a 'track_extractor' function that takes each item and returns the actual track dict,

    This function:
        1) Iterates over each item
        2) Extracts the track dict
        3) Calls `save_or_update_track(track_data)`
        4) Links the resulting Track to container_obj.tracks
    """
    with transaction.atomic():
        # If you want a "fresh" sync, you could do:
        # container_obj.tracks.clear()

        for item in tqdm(
            track_items, desc="Processing tracks for playlist", unit="track"
        ):
            track_data = track_extractor(item)
            if not track_data:
                continue  # local/unavailable or missing track

            track_obj = save_or_update_track(track_data)
            if track_obj:
                container_obj.tracks.add(track_obj[0])


def _fetch_all_items(sp, fetch_func, *args, **kwargs):
    """
    A generic helper to fetch multiple “pages” of items from Spotify.
    - `sp` is your Spotipy client
    - `fetch_func` is a Spotipy method like `sp.playlist_items` or `sp.album_tracks`
    - `args` and `kwargs` are passed on to that method
    Returns a list of all items across all pages.
    """
    all_items = []
    results_page = fetch_func(*args, **kwargs)

    while True:
        items_on_page = results_page.get("items", [])
        all_items.extend(items_on_page)

        next_url = results_page.get("next")
        if next_url:
            results_page = sp.next(results_page)
        else:
            break

    return all_items


def _fetch_all_playlist_items(sp, playlist_id):
    """
    Returns a list of all items in a playlist, each item being a dict with a "track" key.
    """
    return _fetch_all_items(sp, sp.playlist_items, playlist_id)


def get_or_create_album(album_data) -> Album:
    """
    Given a Spotify 'album' dictionary, extract the relevant fields
    and create or update the corresponding Album object in the database.

    Returns:
        Album object if album_id is present,
        otherwise None (if album_data is empty or missing an 'id').
    """
    album_id = album_data.get("id")  # e.g. "5TccnXy13kDWZfVAKn2Wp5"
    if not album_id:
        return None  # No album_id, so we skip creating an Album

    # Extract fields
    album_name = album_data.get("name", "")
    album_type = album_data.get("album_type", "")
    release_date = album_data.get("release_date", "")
    release_date_precision = album_data.get("release_date_precision", "")
    total_tracks = album_data.get("total_tracks", 0)
    album_href = album_data.get("href", "")
    album_uri = album_data.get("uri", "")

    # Extract the album’s Spotify URL if present
    album_external_urls = album_data.get("external_urls", {})
    album_spotify_url = album_external_urls.get("spotify", "")

    # Optional: store the first album cover image
    images = album_data.get("images", [])
    album_art = images[0].get("url", "") if images else ""

    # Create or update Album
    album_obj, _created = Album.objects.update_or_create(
        album_id=album_id,
        defaults={
            "name": album_name,
            "album_type": album_type,
            "release_date": release_date,
            "release_date_precision": release_date_precision,
            "total_tracks": total_tracks,
            "spotify_url": album_spotify_url,
            "href": album_href,
            "uri": album_uri,
            "art": album_art,
        },
    )
    artists_data = album_data.get("artists", [])  # a list of artist dicts
    artist_objs = []

    for artist_data in artists_data:
        # Use your existing helper to avoid duplicating logic
        artist_obj = get_or_create_artist(artist_data)
        if artist_obj:
            artist_objs.append(artist_obj)

    # Use a transaction so all artist linking is atomic
    with transaction.atomic():
        # Replace the old set of artists with the new ones
        album_obj.artists.set(artist_objs)
    return album_obj


def _update_artist_genres(artist_obj: Artist, genre_list: list[str]) -> None:
    """
    Given an Artist object and a list of genre strings,
    create (if needed) the corresponding Genre records,
    and set artist_obj.genres to match this list.
    """
    genre_objs = []
    for genre_name in genre_list:
        if genre_name.strip():
            # get_or_create ensures we don’t duplicate genres
            try:
                genre_obj, _ = Genre.objects.get_or_create(name=genre_name.strip())
                genre_objs.append(genre_obj)

            except django.db.utils.OperationalError as e:
                if "SAVEPOINT" in str(e):
                    continue
                else:
                    raise              

    # Atomically set the Artist's genres in one go
    with transaction.atomic():
        artist_obj.genres.set(genre_objs)


def get_or_create_artist(artist_data) -> Artist:
    """
    Given a Spotify 'artist' dictionary, attempt to get or create an Artist record
    without updating any existing one. Returns the Artist instance or None if 'id' missing.
    """
    artist_id = artist_data.get("id")
    if not artist_id:
        return None  # Skip if the artist has no Spotify ID (e.g., local/unavailable)
    
    # handling weird input
    name = artist_data.get("name")
    if name is None:
        # Option 1: Provide a default value
        name = "Unknown Artist"
        # return None
    
    print('update or create Artist attempt')
    print(artist_data)
        
    artist_obj, _created = Artist.objects.update_or_create(
        artist_id=artist_id,
        defaults={
            "href": artist_data.get("href", ""),
            "type": artist_data.get("type", "artist"),
            "uri": artist_data.get("uri", ""),
            "external_urls": artist_data.get("external_urls", {}),
            "name": artist_data.get("name", ""),
            "followers": (
                artist_data["followers"]["total"] if artist_data.get("followers") else 0
            ),
            "images": [
                {"url": img["url"], "height": img["height"], "width": ["img.width"]}
                for img in artist_data.get("images", [])
            ],
            "popularity": artist_data.get("popularity", 0),
        },
    )
    genre_list = artist_data.get("genres", [])
    if genre_list:
        _update_artist_genres(artist_obj, genre_list)

    return artist_obj


def save_or_update_track(track_data) -> Track:
    """
    Given a Spotify track dictionary:
    1) Create/Update the 'Album' via get_or_create_album().
    2) Create/Update the 'Track' itself (fields like name, duration, etc.).
    3) Create/Update and link any associated 'Artist' records via get_or_create_artist().

    Returns:
        Track object or None if track_data missing 'id'.
    """
    if not track_data:
        return None
    
    # 1. Basic track fields
    track_id = track_data.get("id")
    if not track_id:
        return None  # Skip if there's no Spotify track ID (local track, etc.)

    track_name = track_data.get("name", "")
    disc_number = track_data.get("disc_number", 1)
    track_number = track_data.get("track_number", 1)
    duration_ms = track_data.get("duration_ms", 0)
    explicit = track_data.get("explicit", False)
    href = track_data.get("href", "")
    popularity = track_data.get("popularity", 0)
    is_playable = track_data.get("is_playable", True)
    is_local = track_data.get("is_local", False)

    # 2. Album handling
    album_data = track_data.get("album", {})
    album_obj = get_or_create_album(album_data)

    # 3. External URLs, preview, URI
    external_urls = track_data.get("external_urls", {})
    spotify_url = external_urls.get("spotify", "")
    preview_url = track_data.get("preview_url", "")
    uri = track_data.get("uri", "")

    print('prep-track')
    # 4. Update or create the Track
    track_obj, _created = Track.objects.update_or_create(
        track_id=track_id,
        defaults={
            "name": track_name,
            "album": album_obj,
            "disc_number": disc_number,
            "track_number": track_number,
            "duration_ms": duration_ms,
            "explicit": explicit,
            "href": href,
            "spotify_url": spotify_url,
            "uri": uri,
            "preview_url": preview_url,
            "popularity": popularity,
            "is_playable": is_playable,
            "is_local": is_local,
            "art": (
                track_data["album"]["images"][0]["url"]
                if track_data["album"] and track_data["album"]["images"]
                else None
            ),
        },
    )

    print('track come out')

    # 5. Handle track artists (M2M)
    artists_data = track_data.get("artists", [])
    artist_objs = []
    for artist_data in artists_data:
        try:
            artist_obj = get_or_create_artist(artist_data)
        except django.db.utils.OperationalError as e:
            if "SAVEPOINT" in str(e):
                continue
            else:
                raise  
        if artist_obj:
            artist_objs.append(artist_obj)

    # with transaction.atomic():
        track_obj.artists.set(artist_objs)
    print('tell me what this is')
    return track_obj, track_id
    #return track_obj


def get_track(sp, track_id):
    track = sp.track(track_id)
    return track.model_dump()


if __name__ == "__main__":
    pass
