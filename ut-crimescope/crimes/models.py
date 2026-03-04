from django.db import models
from django.contrib.auth.models import AbstractUser

# Each Building on campus gets one row here
class Building(models.Model):
    name = models.CharField(max_length=255)
    abberviation = models.CharField(max_length=20, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    zone = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return self.name
    
# Each crime reported by UTPD gets one row here
class Incident(models.Model):
    incident_id = models.CharField(max_length=50, unique=True)
    reported_date = models.DateField(db_index=True)
    reported_time = models.TimeField(null=True, blank=True)
    occurred_date = models.DateField(null=True, blank=True)
    occurred_time = models.TimeField(null=True, blank=True)
    crime_type = models.CharField(max_length=200, db_index=True)
    location_raw = models.CharField(max_length=300)
    building = models.ForeignKey(
        Building,
        null = True,
        blank = True,
        on_delete = models.SET_NULL
    )
    campus_zone = models.CharField(max_length=50, blank=True)
    disposition = models.CharField(max_length=200, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    scraped_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.incident_id} — {self.crime_type}" 
    
class UserProfile(AbstractUser):
    watched_buildings = models.ManyToManyField(Building, blank=True)
    alert_crime_types = models.CharField(max_length=500, blank=True)

class WatchedLocation(models.Model):
    RADIUS_CHOICES = [
        (0.10, 'Within 1 block (~0.1 mi)'),
        (0.25, 'Within a few blocks (~0.25 mi)'),
        (0.50, 'Within half a mile'),
        (1.00, 'Within 1 mile'),
    ]
    user         = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='watched_locations')
    label        = models.CharField(max_length=200)   # the address/name the user typed
    latitude     = models.FloatField()
    longitude    = models.FloatField()
    radius_miles = models.FloatField(choices=RADIUS_CHOICES, default=0.25)
    created_at   = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.label} ({self.radius_miles} mi) — {self.user.username}"


class AlertLog(models.Model):
    user     = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE)
    sent_at  = models.DateTimeField(auto_now_add=True)
    
    