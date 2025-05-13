# users/serializers.py
from rest_framework import serializers
from .models import User, UserTopArtist, UserTopTrack, UserSavedAlbums, Reviews, SoundscapeUser
from music.serializers import ArtistSerializer, TrackSerializer, AlbumSerializer


class SoundscapeUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = SoundscapeUser
        fields = "__all__"

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"


class UserTopArtistSerializer(serializers.ModelSerializer):
    artist = ArtistSerializer(read_only=True)

    class Meta:
        model = UserTopArtist
        fields = ['artist', "time_range", "rank", "user"]


class UserTopTrackSerializer(serializers.ModelSerializer):
    track = TrackSerializer(read_only=True)

    class Meta:
        model = UserTopTrack
        fields = ['track', 'time_range', 'rank', 'user']



class UserSavedAlbumsSerializer(serializers.ModelSerializer):
    album = AlbumSerializer(read_only=True)
    class Meta:
        model = UserSavedAlbums
        fields = "__all__"


class ReviewSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    track = TrackSerializer(read_only=True)
    class Meta:
        model = Reviews
        fields = "__all__"
