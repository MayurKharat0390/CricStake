import os
import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from predictions.models import Match, Team, Player

class Command(BaseCommand):
    help = "Fetches actual scheduled cricket matches from the API and populates the database."

    def add_arguments(self, parser):
        parser.add_argument(
            '--simulate',
            action='store_true',
            help='Fetch a simulated list of real upcoming IPL matches without needing an API key.',
        )

    def handle(self, *args, **options):
        simulate = options['simulate']
        api_key = getattr(settings, 'CRICKET_DATA_API_KEY', os.environ.get('CRICKET_DATA_API_KEY', ''))

        self.stdout.write(self.style.MIGRATE_HEADING("=== CricStake Real Match Timetable Sync ==="))

        if not api_key and not simulate:
            self.stdout.write(self.style.WARNING(
                "No 'CRICKET_DATA_API_KEY' found in environment or Django settings.\n"
                "Running in SIMULATION MODE to load real IPL timetable matches!"
            ))
            simulate = True

        if simulate:
            self.stdout.write(self.style.WARNING("Simulating real-world API match timetable load..."))
            self.run_simulation()
        else:
            self.stdout.write(self.style.SUCCESS(f"Connecting to live CricketData API using key: ...{api_key[-6:] if len(api_key) > 6 else 'keyset'}"))
            self.run_live_api(api_key)

    def generate_placeholder_logo(self, short_name):
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="w-12 h-12">
            <defs>
                <linearGradient id="grad_{short_name}" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#6366f1"/>
                    <stop offset="100%" stop-color="#10b981"/>
                </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="45" fill="url(#grad_{short_name})" stroke="#FFFFFF" stroke-opacity="0.1" stroke-width="2"/>
            <text x="50" y="52" text-anchor="middle" dominant-baseline="central" fill="#FFFFFF" font-family="system-ui, sans-serif" font-weight="bold" font-size="28">{short_name}</text>
        </svg>"""

    def process_matches(self, matches_list):
        count = 0
        now = timezone.now()

        for m_data in matches_list:
            api_id = m_data.get("id")
            name = m_data.get("name", "")
            match_type = m_data.get("matchType", "")
            status_text = m_data.get("status", "")
            
            # We want upcoming/live matches, or matches that aren't settled yet
            if "ended" in status_text.lower() or "result" in status_text.lower() or "won" in status_text.lower() or "completed" in status_text.lower():
                continue

            # Parse dateTimeGMT or date
            dt_str = m_data.get("dateTimeGMT")
            match_dt = None
            if dt_str:
                try:
                    # Clean the Z if it exists for parsing
                    if dt_str.endswith('Z'):
                        dt_str = dt_str[:-1]
                    dt = datetime.fromisoformat(dt_str)
                    from django.utils.timezone import is_naive, make_aware, utc
                    if is_naive(dt):
                        match_dt = make_aware(dt, utc)
                    else:
                        match_dt = dt
                except Exception:
                    pass

            if not match_dt:
                # Fallback to date
                date_str = m_data.get("date")
                if date_str:
                    try:
                        match_dt = timezone.make_aware(datetime.strptime(date_str, "%Y-%m-%d"))
                    except Exception:
                        continue
                else:
                    continue

            # Filter out matches older than 1 day in the past to keep timetable clean
            if match_dt < now - timezone.timedelta(days=1):
                continue

            # Parse Teams
            team_info = m_data.get("teamInfo", [])
            teams = m_data.get("teams", [])

            if len(teams) < 2:
                # Try to extract from name "Team A vs Team B"
                if " vs " in name:
                    teams = name.split(" vs ")
                else:
                    continue

            t1_name = teams[0].strip()
            t2_name = teams[1].strip()

            t1_short = t1_name[:3].upper()
            t2_short = t2_name[:3].upper()

            if len(team_info) >= 2:
                t1_short = team_info[0].get("shortname", t1_short)
                t2_short = team_info[1].get("shortname", t2_short)

            # Create or get Teams
            team_a, _ = Team.objects.get_or_create(
                short_name=t1_short,
                defaults={
                    "name": t1_name,
                    "logo_svg": self.generate_placeholder_logo(t1_short)
                }
            )

            team_b, _ = Team.objects.get_or_create(
                short_name=t2_short,
                defaults={
                    "name": t2_name,
                    "logo_svg": self.generate_placeholder_logo(t2_short)
                }
            )

            # Create or update Match
            match, created = Match.objects.update_or_create(
                api_match_id=api_id,
                defaults={
                    "team_a": team_a,
                    "team_b": team_b,
                    "match_datetime": match_dt,
                    "status": "upcoming"
                }
            )

            # Add a couple of dummy players for teams if they have no players
            for team in [team_a, team_b]:
                if not team.players.exists():
                    Player.objects.create(name=f"Captain {team.short_name}", team=team)
                    Player.objects.create(name=f"Bowler {team.short_name}", team=team)
                    Player.objects.create(name=f"All-rounder {team.short_name}", team=team)

            from django.utils.timezone import template_localtime
            local_dt = template_localtime(match_dt)
            status_label = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"[OK] {status_label} match: {team_a.short_name} vs {team_b.short_name} on {local_dt.strftime('%b %d, %I:%M %p')} (API ID: {api_id})"))
            count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully processed {count} upcoming matches!"))

    def run_live_api(self, api_key):
        url = "https://api.cricketdata.org/v1/matches"
        try:
            response = requests.get(url, params={"apikey": api_key, "offset": 0}, timeout=15)
            if response.status_code == 200:
                payload = response.json()
                if payload.get("status") == "success":
                    matches_list = payload.get("data", [])
                    self.process_matches(matches_list)
                else:
                    self.stdout.write(self.style.ERROR(f"API Error payload: {payload.get('reason', 'Unknown error')}"))
            else:
                self.stdout.write(self.style.ERROR(f"HTTP Error {response.status_code} querying CricketData API."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Network error querying API: {e}"))

    def run_simulation(self):
        # High fidelity mock upcoming timetable matches
        now = timezone.now()
        
        # Helper to construct a specific date relative to 'now'
        def get_iso_time(days_offset, hour, minute):
            target = (now + timezone.timedelta(days=days_offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            return target.isoformat()

        mock_matches = [
            {
                "id": "live-ipl-match-1",
                "name": "Kolkata Knight Riders vs Mumbai Indians",
                "matchType": "t20",
                "status": "Match scheduled",
                "dateTimeGMT": get_iso_time(0, 19, 30),
                "teams": ["Kolkata Knight Riders", "Mumbai Indians"],
                "teamInfo": [
                    {"name": "Kolkata Knight Riders", "shortname": "KKR"},
                    {"name": "Mumbai Indians", "shortname": "MI"}
                ]
            },
            {
                "id": "live-ipl-match-2",
                "name": "Gujarat Titans vs Chennai Super Kings",
                "matchType": "t20",
                "status": "Match scheduled",
                "dateTimeGMT": get_iso_time(1, 19, 30),
                "teams": ["Gujarat Titans", "Chennai Super Kings"],
                "teamInfo": [
                    {"name": "Gujarat Titans", "shortname": "GT"},
                    {"name": "Chennai Super Kings", "shortname": "CSK"}
                ]
            },
            {
                "id": "live-ipl-match-3",
                "name": "Sunrisers Hyderabad vs Royal Challengers Bengaluru",
                "matchType": "t20",
                "status": "Match scheduled",
                "dateTimeGMT": get_iso_time(2, 19, 30),
                "teams": ["Sunrisers Hyderabad", "Royal Challengers Bengaluru"],
                "teamInfo": [
                    {"name": "Sunrisers Hyderabad", "shortname": "SRH"},
                    {"name": "Royal Challengers Bengaluru", "shortname": "RCB"}
                ]
            },
            {
                "id": "live-ipl-match-4",
                "name": "Lucknow Super Giants vs Punjab Kings",
                "matchType": "t20",
                "status": "Match scheduled",
                "dateTimeGMT": get_iso_time(3, 19, 30),
                "teams": ["Lucknow Super Giants", "Punjab Kings"],
                "teamInfo": [
                    {"name": "Lucknow Super Giants", "shortname": "LSG"},
                    {"name": "Punjab Kings", "shortname": "PBKS"}
                ]
            },
            {
                "id": "live-ipl-match-5",
                "name": "Mumbai Indians vs Rajasthan Royals",
                "matchType": "t20",
                "status": "Match scheduled",
                "dateTimeGMT": get_iso_time(4, 15, 30),
                "teams": ["Mumbai Indians", "Rajasthan Royals"],
                "teamInfo": [
                    {"name": "Mumbai Indians", "shortname": "MI"},
                    {"name": "Rajasthan Royals", "shortname": "RR"}
                ]
            },
            {
                "id": "live-ipl-match-6",
                "name": "Kolkata Knight Riders vs Delhi Capitals",
                "matchType": "t20",
                "status": "Match scheduled",
                "dateTimeGMT": get_iso_time(4, 19, 30),
                "teams": ["Kolkata Knight Riders", "Delhi Capitals"],
                "teamInfo": [
                    {"name": "Kolkata Knight Riders", "shortname": "KKR"},
                    {"name": "Delhi Capitals", "shortname": "DC"}
                ]
            }
        ]

        self.process_matches(mock_matches)
