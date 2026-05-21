import random
import string
from django.utils import timezone
from django.db import models, transaction
from django.db.models import Sum
from datetime import timedelta, date
from .models import Room, Prediction, Badge, UserBadge, WeeklyChampion, UserProfile, User

# 1. Generate unique 6-character invite code
def generate_invite_code():
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choice(chars) for _ in range(6))
        if not Room.objects.filter(invite_code=code).exists():
            return code


# 2. Check and Award Badges
def award_badges(user):
    profile = user.profile
    
    # Pre-fetch existing badge names to avoid duplicates
    earned_badge_names = set(UserBadge.objects.filter(user=user).values_list('badge__name', flat=True))

    badges_to_check = [
        {
            'name': 'First Win',
            'description': 'Awarded for your first correct prediction!',
            'icon': '🏆',
            'condition': profile.correct_predictions >= 1
        },
        {
            'name': '3-Match Streak',
            'description': 'Awarded for getting 3 correct predictions in a row!',
            'icon': '🔥',
            'condition': profile.longest_streak >= 3
        },
        {
            'name': 'Top Predictor',
            'description': 'Awarded for reaching 10 correct predictions!',
            'icon': '⚡',
            'condition': profile.correct_predictions >= 10
        }
    ]

    for b_data in badges_to_check:
        if b_data['name'] not in earned_badge_names and b_data['condition']:
            # Get or create badge definition
            badge, _ = Badge.objects.get_or_create(
                name=b_data['name'],
                defaults={'description': b_data['description'], 'icon': b_data['icon']}
            )
            # Award to user
            UserBadge.objects.get_or_create(user=user, badge=badge)


# 3. Settle Predictions for a Match
def settle_match_predictions(match):
    """
    Settles all predictions for a specific match depending on its status.
    If 'completed': marks wins/losses, pays out coins, updates streaks and awards badges.
    If 'abandoned': refunds bet amounts to users.
    """
    if match.status not in ['completed', 'abandoned']:
        return

    # Settle in a single atomic transaction
    with transaction.atomic():
        predictions = Prediction.objects.filter(match=match, status='pending')

        for pred in predictions:
            user = pred.user
            profile = user.profile

            if match.status == 'abandoned':
                # Refund bet
                pred.status = 'refunded'
                pred.coins_change = 0
                profile.coin_balance += pred.bet_amount
                profile.save()
                pred.save()
                continue

            # Settle completed match
            correct = False
            result_obj = None

            if pred.market_type == 'winner':
                result_obj = match.winner
            elif pred.market_type == 'toss':
                result_obj = match.toss_winner
            elif pred.market_type == 'pom':
                result_obj = match.player_of_match
            elif pred.market_type == 'top_batter':
                result_obj = match.top_batter
            elif pred.market_type == 'top_bowler':
                result_obj = match.top_bowler

            # Check correctness
            if result_obj and pred.selected_value == str(result_obj.id):
                correct = True

            if correct:
                pred.status = 'won'
                payout = int(round(pred.bet_amount * float(pred.multiplier)))
                pred.coins_change = payout - pred.bet_amount
                
                # Add payout to balance
                profile.coin_balance += payout
                profile.total_predictions += 1
                profile.correct_predictions += 1
                profile.current_streak += 1
                if profile.current_streak > profile.longest_streak:
                    profile.longest_streak = profile.current_streak
            else:
                pred.status = 'lost'
                pred.coins_change = -pred.bet_amount
                
                # No balance change (already deducted on placement)
                profile.total_predictions += 1
                profile.current_streak = 0

            profile.save()
            pred.save()
            
            # Check badges
            award_badges(user)


# 4. Calculate Weekly Champions for a Room
def calculate_weekly_champions(room, check_date=None):
    """
    Computes weekly champions for a specific room.
    The week starts on Monday and ends on Sunday of the week containing check_date (default: today).
    """
    if check_date is None:
        check_date = date.today()

    # Find the Monday of that week
    week_start = check_date - timedelta(days=check_date.weekday())
    week_end = week_start + timedelta(days=6)

    # Calculate net profit (won predictions settled on matches starting this week)
    # We find won predictions in this room during the week
    won_preds = Prediction.objects.filter(
        room=room,
        status='won',
        match__match_datetime__date__range=[week_start, week_end]
    )

    # Group by user and aggregate coin profit
    # net coin profit = Sum(coins_change)
    profits = won_preds.values('user').annotate(total_profit=Sum('coins_change')).order_by('-total_profit')

    if not profits or profits[0]['total_profit'] is None or profits[0]['total_profit'] <= 0:
        # No one had positive earnings this week
        return None

    best_user_id = profits[0]['user']
    best_user = User.objects.get(id=best_user_id)

    # Award the Weekly Champion Record
    champ, created = WeeklyChampion.objects.get_or_create(
        room=room,
        week_start=week_start,
        defaults={'user': best_user}
    )

    # Award "Weekly Champion" badge
    badge, _ = Badge.objects.get_or_create(
        name='Weekly Champion',
        defaults={
            'description': 'Awarded for dominating a room leaderboard as the Weekly Champion!',
            'icon': '👑'
        }
    )
    UserBadge.objects.get_or_create(user=best_user, badge=badge)

    return champ


def auto_sync_completed_matches():
    """
    Automatically checks for matches that have passed their scheduled start time
    and syncs their outcomes either via the live API or using a simulated result.
    This is called on user dashboard/room views to enable automatic lazy-settlement.
    """
    from .models import Match, Team, Player
    from django.conf import settings
    import os
    import requests
    
    now = timezone.now()
    
    # 1. Fetch matches scheduled in the past that are still marked as upcoming or live
    past_matches = Match.objects.filter(status__in=['upcoming', 'live'], match_datetime__lte=now)
    
    if not past_matches.exists():
        return
        
    api_key = getattr(settings, 'CRICKET_DATA_API_KEY', os.environ.get('CRICKET_DATA_API_KEY', ''))
    
    for match in past_matches:
        # If API key is configured and this match has a real API ID
        if api_key and match.api_match_id and not match.api_match_id.startswith('mock-'):
            # Only poll if the match started more than 4 hours ago (realistic game duration)
            if now >= match.match_datetime + timedelta(hours=4):
                url = "https://api.cricketdata.org/v1/match_info"
                try:
                    response = requests.get(url, params={"apikey": api_key, "id": match.api_match_id}, timeout=4)
                    if response.status_code == 200:
                        payload = response.json()
                        if payload.get("status") == "success" and payload.get("data", {}).get("matchEnded"):
                            data = payload.get("data", {})
                            
                            # Resolve Toss
                            toss_name = data.get("tossWinner")
                            if toss_name:
                                toss_winner = Team.objects.filter(name__icontains=toss_name).first() or Team.objects.filter(short_name__icontains=toss_name).first()
                                if toss_winner:
                                    match.toss_winner = toss_winner
                                
                            # Resolve Winner
                            winner_name = data.get("winner")
                            if winner_name:
                                winner = Team.objects.filter(name__icontains=winner_name).first() or Team.objects.filter(short_name__icontains=winner_name).first()
                                if winner:
                                    match.winner = winner
                                    match.status = 'completed'
                            elif "abandoned" in data.get("status", "").lower() or "no result" in data.get("status", "").lower():
                                match.status = 'abandoned'
                                
                            # Resolve POM
                            pom_name = data.get("playerOfMatch")
                            if pom_name:
                                match.player_of_match = Player.objects.filter(name__icontains=pom_name).first()
                                
                            # Resolve Batter & Bowler
                            batter_name = data.get("topBatter") or pom_name
                            if batter_name:
                                match.top_batter = Player.objects.filter(name__icontains=batter_name).first()
                                
                            bowler_name = data.get("topBowler")
                            if bowler_name:
                                match.top_bowler = Player.objects.filter(name__icontains=bowler_name).first()
                                
                            match.save()
                            settle_match_predictions(match)
                except Exception:
                    pass
        else:
            # Simulation / Demo fallback
            # Automatically settle past matches with a realistic simulation result
            # Set to completed so it processes the user payouts immediately!
            
            short_pair = {match.team_a.short_name, match.team_b.short_name}
            
            if "CSK" in short_pair and "SRH" in short_pair:
                winner_team = Team.objects.filter(short_name="SRH").first() or match.team_b
                toss_winner_team = Team.objects.filter(short_name="SRH").first() or match.team_b
                pom_player = Player.objects.filter(name__icontains="Travis Head").first() or Player.objects.filter(team=winner_team).first()
                top_batter_player = Player.objects.filter(name__icontains="Travis Head").first() or Player.objects.filter(team=winner_team).first()
                top_bowler_player = Player.objects.filter(name__icontains="Pat Cummins").first() or Player.objects.filter(team=winner_team).first()
            elif "RR" in short_pair and "LSG" in short_pair:
                winner_team = Team.objects.filter(short_name="RR").first() or match.team_a
                toss_winner_team = Team.objects.filter(short_name="RR").first() or match.team_a
                pom_player = Player.objects.filter(name__icontains="Vaibhav Sooryavanshi").first() or Player.objects.filter(team=winner_team).first()
                top_batter_player = Player.objects.filter(name__icontains="Vaibhav Sooryavanshi").first() or Player.objects.filter(team=winner_team).first()
                top_bowler_player = Player.objects.filter(name__icontains="Yuzvendra Chahal").first() or Player.objects.filter(team=winner_team).first()
            elif "KKR" in short_pair and "MI" in short_pair:
                winner_team = Team.objects.filter(short_name="KKR").first() or match.team_a
                toss_winner_team = Team.objects.filter(short_name="KKR").first() or match.team_a
                pom_player = Player.objects.filter(name__icontains="Ajinkya Rahane").first() or Player.objects.filter(team=winner_team).first()
                top_batter_player = Player.objects.filter(name__icontains="Corbin Bosch").first() or Player.objects.filter(team=match.team_b).first()
                top_bowler_player = Player.objects.filter(name__icontains="Mitchell Starc").first() or Player.objects.filter(team=winner_team).first()
            else:
                # General case: match-team-aware outcome
                winner_team = match.team_a
                toss_winner_team = match.team_b
                pom_player = Player.objects.filter(team=winner_team).first()
                top_batter_player = Player.objects.filter(team=winner_team).first()
                top_bowler_player = Player.objects.filter(team=toss_winner_team).first()
            
            # Fallback if players don't exist
            if not pom_player:
                pom_player = Player.objects.filter(team=winner_team).first() or Player.objects.create(name=f"Captain {winner_team.short_name}", team=winner_team)
            if not top_batter_player:
                top_batter_player = Player.objects.filter(team=winner_team).first() or Player.objects.create(name=f"Batter {winner_team.short_name}", team=winner_team)
            if not top_bowler_player:
                top_bowler_player = Player.objects.filter(team=toss_winner_team).first() or Player.objects.create(name=f"Bowler {toss_winner_team.short_name}", team=toss_winner_team)
            
            match.toss_winner = toss_winner_team
            match.winner = winner_team
            match.status = 'completed'
            match.player_of_match = pom_player
            match.top_batter = top_batter_player
            match.top_bowler = top_bowler_player
            match.save()
            settle_match_predictions(match)
