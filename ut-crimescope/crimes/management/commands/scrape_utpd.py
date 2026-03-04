import io
import re
import time
import requests
import pdfplumber
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils.dateparse import parse_date, parse_time
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from crimes.models import Incident, Building, WatchedLocation, AlertLog

BUILDING_MAP = {
    # Maps text fragments from UTPD location strings to known buildings.
    # Expand this as you see new location strings in the PDF.
    "WELCH": "Welch Hall",
    "PCL": "Perry-Castañeda Library",
    "RLM": "Robert Lee Moore Hall",
    "GDC": "Gates Dell Complex",
    "UNB": "University Blvd",
    "JESTER": "Jester Center",
    "LITTLEFIELD": "Littlefield Home",
    "SAC": "Student Activity Center",
    "UNION": "Texas Union",
    "SPEEDWAY": "Speedway",
}


def normalize_building(text):
    """Keyword-match against any text (full merged line for best coverage)."""
    upper = text.upper()
    for keyword, building_name in BUILDING_MAP.items():
        if keyword in upper:
            return building_name
    return None


# Matches one offense entry. Both offense and address use lazy matching,
# anchored by the two MM/DD/YYYY date fields that always appear in order.
# No $ at end — allows trailing content from wrapped address/offense lines.
OFFENSE_RE = re.compile(
    r'^(?:(?P<inci_id>\d{8})\s+)?'              # optional 8-digit incident ID
    r'(?P<off_num>\d+)\s*-\s+'                  # offense number (1, 2, 3 ...)
    r'(?P<offense>.+?)\s+'                      # offense description (lazy)
    r'(?P<rept_date>\d{2}/\d{2}/\d{4})\s+'     # reported date MM/DD/YYYY
    r'(?P<rept_hour>\d{4})\s+'                  # reported hour HHMM
    r'(?P<address>.+?)\s+'                      # street address (lazy)
    r'(?P<occu_date>\d{2}/\d{2}/\d{4})\s+'     # occurred date MM/DD/YYYY
    r'(?P<occu_hour>\d{4})\s+'                  # occurred hour HHMM
    r'(?P<status>[A-Z]+)'                       # case status code
)

# Identifies lines that open a new offense record vs. address/offense wraps
NEW_RECORD_RE = re.compile(r'^(?:\d{8}\s+)?\d+\s*-\s+\S')


def parse_utpd_date(date_str):
    """Convert 'MM/DD/YYYY' → Django date."""
    try:
        m, d, y = date_str.split("/")
        return parse_date(f"{y}-{m.zfill(2)}-{d.zfill(2)}")
    except Exception:
        return None


def parse_utpd_hour(hour_str):
    """Convert '1425' → parse_time('14:25')."""
    if hour_str and len(hour_str) == 4:
        return parse_time(f"{hour_str[:2]}:{hour_str[2:]}")
    return None


def extract_records(text):
    """
    Parse raw text from one PDF page into a list of record dicts.

    pdfplumber reads PDF text left-to-right across the full row width, so
    long offense names and addresses that wrap visually appear as extra lines
    between offense records. We merge those continuation lines back into the
    offense line above them before applying the regex.
    """
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Merge continuation lines (address/offense wraps) into the offense line above
    merged_lines = []
    for line in raw_lines:
        if NEW_RECORD_RE.match(line):
            merged_lines.append(line)
        elif merged_lines:
            merged_lines[-1] += ' ' + line
        # else: page header before any records — skip

    records = []
    current_inci_id = None

    for line in merged_lines:
        m = OFFENSE_RE.match(line)
        if not m:
            continue

        if m.group('inci_id'):
            current_inci_id = m.group('inci_id')
        if not current_inci_id:
            continue

        records.append({
            'incident_id':    f"{current_inci_id}-{m.group('off_num')}",
            'crime_type':     m.group('offense').strip(),
            'reported_date':  parse_utpd_date(m.group('rept_date')),
            'reported_time':  parse_utpd_hour(m.group('rept_hour')),
            'occurred_date':  parse_utpd_date(m.group('occu_date')),
            'occurred_time':  parse_utpd_hour(m.group('occu_hour')),
            'location_raw':   m.group('address').strip(),
            'disposition':    m.group('status').strip(),
            # Full merged line used for building keyword matching so that
            # wrapped address fragments (e.g. "ST/SPEEDWAY") are included.
            '_search_text':   line,
        })

    return records


_geolocator = Nominatim(user_agent='ut-crimescope', timeout=5)


def geocode_address(address):
    """
    Try to geocode a UTPD location string against Austin, TX.
    Returns (lat, lon) or (None, None) on failure.
    Nominatim requires 1 req/sec — callers must sleep between calls.
    """
    try:
        result = _geolocator.geocode(f"{address}, Austin, TX, USA")
        if result:
            return result.latitude, result.longitude
    except Exception:
        pass
    return None, None


def send_alerts(incident):
    """
    Check every WatchedLocation and email the owner if the incident
    falls within their chosen radius. Skips alerts already sent for
    this incident (idempotent via AlertLog).
    """
    if incident.latitude is None:
        return

    already_alerted = set(
        AlertLog.objects.filter(incident=incident).values_list('user_id', flat=True)
    )

    for wl in WatchedLocation.objects.select_related('user').all():
        if wl.user_id in already_alerted:
            continue
        if not wl.user.email:
            continue

        distance = geodesic(
            (incident.latitude, incident.longitude),
            (wl.latitude, wl.longitude),
        ).miles

        if distance <= wl.radius_miles:
            send_mail(
                subject=f'[UT CrimeScope] {incident.crime_type} near {wl.label}',
                message=(
                    f'A new incident was reported near your watched location "{wl.label}".\n\n'
                    f'Incident:  {incident.crime_type}\n'
                    f'Location:  {incident.location_raw}\n'
                    f'Date:      {incident.reported_date}\n'
                    f'Time:      {incident.reported_time or "unknown"}\n'
                    f'Status:    {incident.disposition}\n'
                    f'Distance:  ~{distance:.2f} miles from {wl.label}\n'
                ),
                from_email='alerts@ut-crimescope.local',
                recipient_list=[wl.user.email],
                fail_silently=True,
            )
            AlertLog.objects.create(user=wl.user, incident=incident)


class Command(BaseCommand):
    help = 'Scrape the UTPD daily crime log PDF and save to database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug', action='store_true',
            help='Print parsed records from the first 3 pages and exit without saving',
        )

    def handle(self, *args, **options):
        url = "https://utdirect.utexas.edu/apps/fasweb/utpd/nlogon/crimelog/"
        self.stdout.write("Fetching UTPD crime log PDF...")

        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            self.stderr.write(f"Failed to fetch PDF: HTTP {response.status_code}")
            return

        new_count = 0
        skip_count = 0

        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            pages = pdf.pages[:3] if options['debug'] else pdf.pages

            for i, page in enumerate(pages):
                text = page.extract_text()
                if not text:
                    continue

                records = extract_records(text)

                if options['debug']:
                    self.stdout.write(f"\n--- Page {i + 1}: {len(records)} records ---")
                    for rec in records[:5]:
                        self.stdout.write(str({k: v for k, v in rec.items() if k != '_search_text'}))
                    continue

                for rec in records:
                    if Incident.objects.filter(incident_id=rec['incident_id']).exists():
                        skip_count += 1
                        continue

                    building_name = normalize_building(rec['_search_text'])
                    building_obj = None
                    if building_name:
                        building_obj, _ = Building.objects.get_or_create(name=building_name)

                    # Geocode the incident location for radius-based alerts.
                    # Sleep 1 s between calls to respect Nominatim's rate limit.
                    lat, lon = geocode_address(rec['location_raw'])
                    time.sleep(1)

                    incident = Incident.objects.create(
                        incident_id=rec['incident_id'],
                        reported_date=rec['reported_date'],
                        reported_time=rec['reported_time'],
                        occurred_date=rec['occurred_date'],
                        occurred_time=rec['occurred_time'],
                        crime_type=rec['crime_type'],
                        location_raw=rec['location_raw'],
                        building=building_obj,
                        disposition=rec['disposition'],
                        latitude=lat,
                        longitude=lon,
                    )
                    send_alerts(incident)
                    new_count += 1

        if not options['debug']:
            self.stdout.write(
                f"Done. {new_count} new incidents added, {skip_count} already existed."
            )
