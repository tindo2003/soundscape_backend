from rest_framework import serializers
from .models import Artist, Track, Album, Genre


class ArtistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artist
        fields = [
            "artist_id",  # Primary key field
            "href",  # URL to Spotify API
            "type",  # Object type
            "uri",  # Spotify URI
            "external_urls",  # External URLs as JSON
            "name",  # Artist name
            "followers",  # Follower details as JSON
            "genres",  # List of genres
            "images",  # List of image dictionaries
            "popularity",  # Popularity score
        ]


class TrackSerializer(serializers.ModelSerializer):
    artists = ArtistSerializer(many=True, read_only=True)  # Serialize artists as a list

    class Meta:
        model = Track
        fields = [
            "track_id",
            "name",
            "album",
            "disc_number",
            "track_number",
            "duration_ms",
            "explicit",
            "href",
            "spotify_url",
            "uri",
            "preview_url",
            "popularity",
            "is_playable",
            "is_local",
            "art",
            "artists",  # Include the nested artists field
        ]


class AlbumSerializer(serializers.ModelSerializer):
    class Meta:
        model = Album
        fields = "__all__"


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = "__all__"
