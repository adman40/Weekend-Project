from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db.models import Count
from django.db.models.functions import ExtractHour
from django.db import connection
from .models import Incident, Building, UserProfile, WatchedLocation
from .forms import RegisterForm, ProfileForm, WatchedLocationForm
import csv
import json


def dashboard(request):
    crime_type_filter = request.GET.get('crime_type', '')

    # Base queryset — optionally narrowed by crime type filter
    qs = Incident.objects.all()
    if crime_type_filter:
        qs = qs.filter(crime_type=crime_type_filter)

    # 20 most recent incidents for the table
    recent = qs.order_by('-reported_date')[:20]

    # All distinct crime types for the filter dropdown
    crime_types = (
        Incident.objects
        .values_list('crime_type', flat=True)
        .distinct()
        .order_by('crime_type')
    )

    # Top 10 crime types for the bar chart (respects filter)
    top_types = (
        qs.values('crime_type')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    type_labels = json.dumps([t['crime_type'] for t in top_types])
    type_data   = json.dumps([t['count'] for t in top_types])

    # Weekly incident trend — parameterized raw SQL (respects filter)
    with connection.cursor() as cursor:
        if crime_type_filter:
            cursor.execute("""
                SELECT DATE_TRUNC('week', reported_date::timestamp) AS week,
                       COUNT(*) AS cnt
                FROM crimes_incident
                WHERE reported_date >= NOW() - INTERVAL '12 months'
                  AND crime_type = %s
                GROUP BY week
                ORDER BY week
            """, [crime_type_filter])
        else:
            cursor.execute("""
                SELECT DATE_TRUNC('week', reported_date::timestamp) AS week,
                       COUNT(*) AS cnt
                FROM crimes_incident
                WHERE reported_date >= NOW() - INTERVAL '12 months'
                GROUP BY week
                ORDER BY week
            """)
        rows = cursor.fetchall()
    trend_labels = json.dumps([str(r[0].date()) for r in rows])
    trend_data   = json.dumps([r[1] for r in rows])

    # Incidents by hour of day (respects filter)
    hour_counts = (
        qs.exclude(reported_time=None)
        .annotate(hour=ExtractHour('reported_time'))
        .values('hour')
        .annotate(count=Count('id'))
        .order_by('hour')
    )
    hour_map    = {row['hour']: row['count'] for row in hour_counts}
    def to_12h(h):
        if h == 0:    return "12 AM"
        elif h < 12:  return f"{h} AM"
        elif h == 12: return "12 PM"
        else:         return f"{h - 12} PM"
    hour_labels = json.dumps([to_12h(h) for h in range(24)])
    hour_data   = json.dumps([hour_map.get(h, 0) for h in range(24)])

    # Hot spots — top 20 locations by incident count (respects filter)
    hot_spots = (
        qs.values('location_raw')
        .annotate(count=Count('id'))
        .order_by('-count')[:20]
    )

    return render(request, 'crimes/dashboard.html', {
        'incidents':         recent,
        'crime_types':       crime_types,
        'crime_type_filter': crime_type_filter,
        'type_labels':       type_labels,
        'type_data':         type_data,
        'trend_labels':      trend_labels,
        'trend_data':        trend_data,
        'hour_labels':       hour_labels,
        'hour_data':         hour_data,
        'hot_spots':         hot_spots,
    })


def register_view(request):
    # Handle new user registration; log them in immediately on success
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = RegisterForm()
    return render(request, 'crimes/register.html', {'form': form})


@login_required  # Redirect to login page if the user isn't authenticated
def profile_view(request):
    # Let users update their watched buildings and alert preferences
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
    else:
        form = ProfileForm(instance=request.user)
    return render(request, 'crimes/profile.html', {'form': form})


@login_required
def watch_location_view(request):
    error = None

    if request.method == 'POST':
        form = WatchedLocationForm(request.POST)
        if form.is_valid():
            query  = form.cleaned_data['location_query']
            radius = float(form.cleaned_data['radius_miles'])

            # Geocode the user's input using OpenStreetMap's free Nominatim API
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent='ut-crimescope')
            try:
                result = geolocator.geocode(f"{query}, Austin, TX, USA", timeout=5)
            except Exception:
                result = None

            if result:
                WatchedLocation.objects.create(
                    user=request.user,
                    label=query,
                    latitude=result.latitude,
                    longitude=result.longitude,
                    radius_miles=radius,
                )
                return redirect('watch_location')
            else:
                error = f'Could not find "{query}" — try a more specific address or building name.'
    else:
        form = WatchedLocationForm()

    watched = WatchedLocation.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'crimes/watch_location.html', {
        'form': form, 'watched': watched, 'error': error,
    })


@login_required
def remove_watch_view(request, pk):
    WatchedLocation.objects.filter(pk=pk, user=request.user).delete()
    return redirect('watch_location')


def building_detail(request, pk):
    # Show all incidents linked to a specific building
    building = get_object_or_404(Building, pk=pk)
    incidents = Incident.objects.filter(building=building).order_by('-reported_date')
    return render(request, 'crimes/building_detail.html', {
        'building': building, 'incidents': incidents
    })


def export_csv(request):
    # Stream all incidents as a downloadable CSV file
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="incidents.csv"'
    writer = csv.writer(response)
    writer.writerow(['Incident ID', 'Date', 'Crime Type', 'Location', 'Disposition'])
    for inc in Incident.objects.all().order_by('-reported_date'):
        writer.writerow([
            inc.incident_id, inc.reported_date,
            inc.crime_type, inc.location_raw, inc.disposition
        ])
    return response
