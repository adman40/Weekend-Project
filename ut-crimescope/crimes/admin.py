from django.contrib import admin
from .models import Building, Incident, UserProfile, AlertLog

# Register your models here.
admin.site.register(Building)
admin.site.register(Incident)
admin.site.register(UserProfile)
admin.site.register(AlertLog)
