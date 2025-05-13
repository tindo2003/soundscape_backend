# Create your models here.
from django.db import models


class Genre(models.Model):
    id = models.AutoField(
        primary_key=True
    )  # Explicitly define an AutoField as primary key
    name = models.CharField(
        max_length=100, unique=True, default="Unknown Genre"
    )  # Unique genre name

    def __str__(self):
        return self.name


class Artist(models.Model):
    artist_id = models.CharField(
        max_length=50, primary_key=True
    )  # Matches `id` in FullArtist
    href = models.URLField()  # Matches `href`
    type = models.CharField(max_length=50, default="artist")  # Matches `type`
    uri = models.CharField(max_length=100)  # Matches `uri`
    external_urls = models.JSONField(default=dict)  # Matches `external_urls`
    name = models.CharField(max_length=255)  # Matches `name`
    followers = models.IntegerField(default=0)
    genres = models.ManyToManyField(
        Genre, related_name="artists"
    )  # Link to Genre model
    images = models.JSONField(default=list)  # Matches `images` (list of dictionaries)
    popularity = models.IntegerField()  # Matches `popularity`

    def __str__(self):
        return self.name


class Album(models.Model):
    album_id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    album_type = models.CharField(max_length=50, null=True, blank=True)
    release_date = models.CharField(max_length=50, null=True, blank=True)
    release_date_precision = models.CharField(max_length=10, null=True, blank=True)
    total_tracks = models.IntegerField(null=True, blank=True)
    spotify_url = models.URLField(null=True, blank=True)
    href = models.URLField(null=True, blank=True)
    uri = models.CharField(max_length=100, null=True, blank=True)
    art = models.CharField(max_length=250, null=True, blank=True)
    artists = models.ManyToManyField(Artist, related_name="albums", blank=True)

    def __str__(self):
        return self.name or "Unnamed Album"


class Track(models.Model):
    track_id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255)
    album = models.ForeignKey(Album, on_delete=models.CASCADE)
    disc_number = models.IntegerField()
    track_number = models.IntegerField()
    duration_ms = models.IntegerField()
    explicit = models.BooleanField(default=False)
    href = models.URLField()
    spotify_url = models.URLField()
    uri = models.CharField(max_length=100)
    preview_url = models.URLField(null=True, blank=True)
    popularity = models.IntegerField()
    is_playable = models.BooleanField(default=True, null=True)
    is_local = models.BooleanField(default=False)
    art = models.CharField(max_length=255, null=True, blank=True)
    artists = models.ManyToManyField(Artist, related_name="tracks", blank=True)

    def __str__(self):
        return self.name


class Playlist(models.Model):
    # The "id" from Spotify (e.g. "0sNseT1nV4br05h7t4FiuT")
    playlist_id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255)
    collaborative = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    external_url = models.URLField(blank=True)
    images = models.JSONField(blank=True, default=list)
    public = models.BooleanField(default=True)
    owner_id = models.CharField(
        max_length=50, blank=True, null=True
    )  # Store the user’s Spotify ID
    uri = models.CharField(max_length=100, blank=True)
    tracks = models.ManyToManyField(Track, related_name="playlists", blank=True)

    def __str__(self):
        return f"{self.name} ({self.playlist_id})"
