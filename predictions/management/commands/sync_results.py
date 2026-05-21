import os
import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from predictions.models import Match, Team, Player
from predictions.utils import settle_match_predictions

class Command(BaseCommand):
    help = "Syncs cricket match outcomes from CricketData.org API and settles predictions."

    def add_arguments(self, parser):
        parser.add_argument(
            '--simulate',
            action='store_true',
            help='Run in simulation mode with realistic mock data to test outcomes immediately.',
        )

    def handle(self, *args, **options):
        simulate = options['simulate']
        
        # 1. Fetch API Key from settings or environment
        api_key = getattr(settings, 'CRICKET_DATA_API_KEY', os.environ.get('CRICKET_DATA_API_KEY', ''))
        
        self.stdout.write(self.style.MIGRATE_HEADING("=== CricStake Auto-Verification Service ==="))
        
        if not api_key and not simulate:
            self.stdout.write(self.style.WARNING(
                "No 'CRICKET_DATA_API_KEY' found in environment or Django settings.\n"
                "Automatically running in SIMULATION MODE so you can see live predictions settle!"
            ))
            simulate = True

        if simulate:
            self.stdout.write(self.style.WARNING("Running in SIMULATION MODE..."))
            self.run_simulation()
        else:
            self.stdout.write(self.style.SUCCESS(f"Running in LIVE API MODE using API Key: ...{api_key[-6:] if len(api_key) > 6 else 'keyset'}"))
            self.run_live_api(api_key)

    def run_simulation(self):
        """
        Runs a simulation mapping real-world CricketData.org API response payloads
        to today's live KKR vs MI match, settling all bets.
        """
        kkr = Team.objects.filter(short_name="KKR").first()
        mi = Team.objects.filter(short_name="MI").first()
        
        if not kkr or not mi:
            self.stdout.write(self.style.ERROR("Error: Kolkata Knight Riders (KKR) or Mumbai Indians (MI) teams not found in database. Please seed first!"))
            return

        match = Match.objects.filter(team_a=kkr, team_b=mi).first()
        if not match:
            match = Match.objects.filter(status__in=["upcoming", "live"]).first()
            if not match:
                self.stdout.write(self.style.WARNING("No active matches found to simulate. Seeding fresh live match..."))
                now = timezone.now()
                match = Match.objects.create(
                    team_a=kkr,
                    team_b=mi,
                    match_datetime=now,
                    status="live",
                    api_match_id="live-ipl-match-1"
                )
        
        if not match.api_match_id:
            match.api_match_id = "live-ipl-match-1"
            match.save()

        self.stdout.write(self.style.NOTICE(f"Targeting Match for Simulation: {match}"))

        mock_response = {
            "status": "success",
            "data": {
                "id": match.api_match_id,
                "name": "Kolkata Knight Riders vs Mumbai Indians",
                "matchEnded": True,
                "status": "Kolkata Knight Riders won by 6 wickets",
                "tossWinner": "Kolkata Knight Riders",
                "tossChoice": "field",
                "winner": "Kolkata Knight Riders",
                "playerOfMatch": "Ajinkya Rahane",
                "topBatter": "Corbin Bosch",
                "topBowler": "Mitchell Starc"
            }
        }

        self.process_payload(match, mock_response["data"])

    def run_live_api(self, api_key):
        """
        Queries CricketData.org for matches with configured api_match_ids
        and updates their outcomes dynamically.
        """
        active_matches = Match.objects.filter(status__in=['upcoming', 'live']).exclude(api_match_id__isnull=True).exclude(api_match_id='')
        
        if not active_matches.exists():
            self.stdout.write(self.style.WARNING("No active matches in the database have an 'api_match_id' configured. Set one in Django admin!"))
            return

        for match in active_matches:
            self.stdout.write(self.style.NOTICE(f"Fetching updates for: {match} (API ID: {match.api_match_id})"))
            
            # API endpoint for Match Info (CricketData.org structure)
            url = f"https://api.cricketdata.org/v1/match_info"
            params = {
                "apikey": api_key,
                "id": match.api_match_id
            }
            
            try:
                response = requests.get(url, params=params, timeout=10)
                if response.status_code != 200:
                    self.stdout.write(self.style.ERROR(f"API Error (HTTP {response.status_code}) for match {match.id}"))
                    continue
                
                payload = response.json()
                if payload.get("status") != "success":
                    self.stdout.write(self.style.ERROR(f"API Error payload: {payload.get('reason', 'Unknown error')}"))
                    continue
                
                data = payload.get("data", {})
                if data.get("matchEnded"):
                    self.process_payload(match, data)
                else:
                    self.stdout.write(self.style.NOTICE(f"Match {match} is still in progress or upcoming according to the API."))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to query API for match {match.id}: {e}"))

    def process_payload(self, match, data):
        """
        Parses the match payload, maps text names to our database foreign keys,
        and executes prediction settlement.
        """
        self.stdout.write(self.style.NOTICE("API reports match has ended. Parsing result details..."))
        
        # 1. Map Toss Winner
        toss_name = data.get("tossWinner")
        toss_winner = self.resolve_team(toss_name)
        if toss_winner:
            match.toss_winner = toss_winner
            self.stdout.write(self.style.SUCCESS(f"[OK] Resolved Toss Winner: {toss_winner}"))
        else:
            self.stdout.write(self.style.WARNING(f"[WARN] Could not resolve Toss Team: '{toss_name}'"))

        # 2. Map Match Winner
        winner_name = data.get("winner")
        winner = self.resolve_team(winner_name)
        if winner:
            match.winner = winner
            match.status = "completed"
            self.stdout.write(self.style.SUCCESS(f"[OK] Resolved Match Winner: {winner}"))
        elif "abandoned" in data.get("status", "").lower() or "no result" in data.get("status", "").lower():
            match.status = "abandoned"
            self.stdout.write(self.style.WARNING("[OK] Match marked as ABANDONED."))
        else:
            self.stdout.write(self.style.WARNING(f"[WARN] Could not resolve Winner Team: '{winner_name}'"))

        # 3. Map Player of the Match
        pom_name = data.get("playerOfMatch")
        player_of_match = self.resolve_player(pom_name, match)
        if player_of_match:
            match.player_of_match = player_of_match
            self.stdout.write(self.style.SUCCESS(f"[OK] Resolved Player of the Match: {player_of_match}"))
        else:
            self.stdout.write(self.style.WARNING(f"[WARN] Could not resolve Player of Match: '{pom_name}'"))

        # 4. Map Top Batter
        batter_name = data.get("topBatter") or pom_name # fallback to POM if not explicitly passed
        top_batter = self.resolve_player(batter_name, match)
        if top_batter:
            match.top_batter = top_batter
            self.stdout.write(self.style.SUCCESS(f"[OK] Resolved Top Batter: {top_batter}"))

        # 5. Map Top Bowler
        bowler_name = data.get("topBowler")
        top_bowler = self.resolve_player(bowler_name, match)
        if top_bowler:
            match.top_bowler = top_bowler
            self.stdout.write(self.style.SUCCESS(f"[OK] Resolved Top Bowler: {top_bowler}"))

        # Save match records
        match.save()
        self.stdout.write(self.style.SUCCESS(f"Match status updated to: {match.get_status_display()}"))

        # 6. Trigger CricStake Prediction Verification & Ledger Payouts!
        self.stdout.write(self.style.MIGRATE_LABEL("Triggering prediction settlement ledger..."))
        settle_match_predictions(match)
        
        self.stdout.write(self.style.SUCCESS(f"=== Successfully settled and verified predictions for match {match.id}! ==="))

    def resolve_team(self, team_name):
        """
        Attempts to find a Team object by matching the name or short name.
        """
        if not team_name:
            return None
        team_name = team_name.strip()
        # Direct exact match or shortname
        team = Team.objects.filter(name__iexact=team_name).first()
        if not team:
            team = Team.objects.filter(short_name__iexact=team_name).first()
        if not team:
            # Fuzzy match (substring)
            team = Team.objects.filter(name__icontains=team_name).first()
        return team

    def resolve_player(self, player_name, match):
        """
        Attempts to resolve a Player object belonging to either team_a or team_b.
        """
        if not player_name:
            return None
        player_name = player_name.strip()
        
        # Check both match teams to narrow search
        allowed_teams = [match.team_a, match.team_b]
        
        player = Player.objects.filter(name__iexact=player_name, team__in=allowed_teams).first()
        if not player:
            player = Player.objects.filter(name__icontains=player_name, team__in=allowed_teams).first()
        if not player:
            # Global fallback
            player = Player.objects.filter(name__icontains=player_name).first()
            
        return player
