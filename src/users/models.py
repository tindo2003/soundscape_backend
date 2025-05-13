from django.db import models
from music.models import Artist, Track, Album, Genre
from django.utils.timezone import now
import uuid

TIME_RANGE_CHOICES = (
    ('short_term', 'Short Term'),
    ('medium_term', 'Medium Term'),
    ('long_term', 'Long Term'),
)


class SoundscapeUser(models.Model):
    """Handles authentication (login status, password, username) for Soundscape users."""

    user_id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True)
    username = models.CharField(max_length=50, unique=True)
    email = models.EmailField(max_length=255, unique=True)
    password = models.CharField(max_length=128, blank=True, null=True)
    google_user_id = models.CharField(
        max_length=255, blank=True, null=True, unique=True
    )
    timestamp = models.DateTimeField(null=True)
    pfp = models.CharField(max_length=128, null=True)
    instagram = models.CharField(max_length=128, null=True)
    x = models.CharField(max_length=128, null=True)
    youtube = models.CharField(max_length=128, null=True)

    profile = models.OneToOneField(
        "User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="soundscape_user",
    )
    forgotPasswordToken = models.CharField(max_length=128, blank=True, null=True)
    forgotPasswordTokenExpiry =  models.DateTimeField(null=True)
    verifyToken = models.CharField(max_length=128, blank=True, null=True)
    verifyTokenExpiry = models.DateTimeField(null=True)
    isVerified = models.BooleanField(default=False)

    def attend_concert(self, concert_id):
        return ConcertAttendance.objects.create(
            user=self,
            concert_id=concert_id
        )
    
    def unattend_concert(self, concert_id):
        return ConcertAttendance.objects.filter(
            user=self,
            concert_id=concert_id
        ).delete()
    
    def is_attending_concert(self, concert_id):
        return self.concert_attendances.filter(concert_id=concert_id).exists()
    
    def get_attending_concerts(self):
        return self.concert_attendances.all().values_list('concert_id', flat=True)

    def __str__(self):
        return self.username

# Create your models here.
class User(models.Model):
    spotify_id = models.CharField(max_length=50, primary_key=True)
    display_name = models.CharField(max_length=100, null=True, blank=True)
    email = models.EmailField(max_length=255, null=True, blank=True)
    country = models.CharField(max_length=2, null=True, blank=True)
    explicit_content = models.BooleanField(default=False)
    external_url = models.URLField(max_length=200, null=True, blank=True)
    followers_count = models.IntegerField(default=0)
    href = models.URLField(max_length=200, null=True, blank=True)
    product = models.CharField(max_length=50, null=True, blank=True)
    uri = models.CharField(max_length=100, null=True, blank=True)

    access_token = models.TextField(null=True, blank=True)
    refresh_token = models.TextField(null=True, blank=True)
    token_expires = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.display_name or self.spotify_id


class UserTopArtist(models.Model):
    TIME_RANGE_CHOICES = [
        ("long_term", "Long Term"),
        ("medium_term", "Medium Term"),
        ("short_term", "Short Term"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE)
    time_range = models.CharField(max_length=20, choices=TIME_RANGE_CHOICES)
    rank = models.IntegerField()
    time_collected = models.DateTimeField(default=now)

    class Meta:
        unique_together = ("user", "artist", "time_range")

    def __str__(self):
        return f"{self.user.display_name} - {self.artist.name} ({self.time_range})"


class UserTopTrack(models.Model):
    TIME_RANGE_CHOICES = [
        ("long_term", "Long Term"),
        ("medium_term", "Medium Term"),
        ("short_term", "Short Term"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    track = models.ForeignKey(Track, on_delete=models.CASCADE)
    time_range = models.CharField(max_length=20, choices=TIME_RANGE_CHOICES)
    rank = models.IntegerField()
    time_collected = models.DateTimeField(default=now)
    recently_listened = models.BooleanField(default=False)
    # only applicable for recently listened tracks
    played_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "track", "time_range")  # Ensure uniqueness

    def __str__(self):
        return f"{self.user.display_name} - {self.track.name} ({self.time_range})"


class UserSavedAlbums(models.Model):

    album = models.ForeignKey(Album, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.CharField(max_length=50, null=True, blank=True)
    spotify_url = models.CharField(max_length=100, null=True, blank=True)
    popularity = models.IntegerField()
    art = models.CharField(max_length=250, null=True, blank=True)

    class Meta:
        unique_together = ("user", "album")  # Ensure uniqueness

    def __str__(self):
        return f"{self.user.display_name} - {self.album.name} ({self.album.album_id})"


class UserGenreListening(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="genre_listenings"
    )
    genre = models.ForeignKey(
        Genre, on_delete=models.CASCADE, related_name="user_listenings"
    )
    listen_count = models.IntegerField(
        default=0
    )  # Count of listens for this genre by the user
    time_collected = models.DateTimeField(default=now)

    time_range = models.CharField(
        max_length=50,
        choices=TIME_RANGE_CHOICES,
        default='short_term'
        )

    def __str__(self):
        return f"{self.user.username} - {self.genre.name}: {self.listen_count}"


class Reviews(models.Model):
    un_id = models.CharField(max_length=100, primary_key=True)
    track = models.ForeignKey(Track, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.CharField(max_length=1000, null=True, blank=True)
    rating = models.IntegerField()
    timestamp = models.DateTimeField()

    # class Meta:
    #   unique_together = ('user', 'track')  # Prevent duplicate entries

    def __str__(self):
        return f"{self.user.display_name} - {self.track.name}"

class FriendRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]
    
    sender = models.ForeignKey(User, related_name="sent_requests", on_delete=models.CASCADE)
    receiver = models.ForeignKey(User, related_name="received_requests", on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("sender", "receiver"),)

    def __str__(self):
        return f"{self.sender.username} -> {self.receiver.username} [{self.status}]"

class Friendship(models.Model):
    user1 = models.ForeignKey(User, related_name="friendship_user1", on_delete=models.CASCADE)
    user2 = models.ForeignKey(User, related_name="friendship_user2", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("user1", "user2"),)

    def __str__(self):
        return f"{self.user1.username} & {self.user2.username}"

class ConcertAttendance(models.Model):
    user = models.ForeignKey(
        SoundscapeUser,
        on_delete=models.CASCADE,
        related_name='concert_attendances'
    )
    concert_id = models.CharField(max_length=255)  # Ticketmaster concert ID
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'concert_id']
        
    def __str__(self):
        return f"{self.user.username} - Concert: {self.concert_id}"

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('concert_invite', 'Concert Invite'),
        # Add other notification types as needed
    )

    recipient = models.ForeignKey(SoundscapeUser, related_name='notifications', on_delete=models.CASCADE)
    sender = models.ForeignKey(SoundscapeUser, related_name='sent_notifications', on_delete=models.CASCADE)
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    concert_id = models.CharField(max_length=255)
    concert_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    event_url = models.URLField(max_length=500, null=True, blank=True) 

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.recipient.username} from {self.sender.username}"

class Chat(models.Model):
    participants = models.ManyToManyField(SoundscapeUser, related_name='chats')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Chat {self.id}"

class Message(models.Model):
    chat = models.ForeignKey(Chat, related_name='messages', on_delete=models.CASCADE)
    sender = models.ForeignKey(SoundscapeUser, related_name='sent_messages', on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Message from {self.sender.username} in Chat {self.chat.id}"
