from django.db import models
from django.utils import timezone

class Concert(models.Model):
    ticketmaster_id = models.CharField(max_length=100, unique=True)
    event_name = models.CharField(max_length=255)
    artist = models.CharField(max_length=255)
    venue = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    date = models.DateTimeField()
    price_range = models.CharField(max_length=100, blank=True)
    genres = models.CharField(max_length=100, blank=True)
    image_url = models.URLField(blank=True)
    event_url = models.URLField()
    popularity_score = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['popularity_score']),
            models.Index(fields=['artist']),
            models.Index(fields=['event_name']),
        ]

    def __str__(self):
        return f"{self.artist} at {self.venue} on {self.date}" 