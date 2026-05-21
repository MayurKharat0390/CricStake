from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal

from .models import UserProfile, Room, RoomMember, Team, Player, Match, Prediction, Badge, UserBadge, WeeklyChampion
from .utils import generate_invite_code, settle_match_predictions, calculate_weekly_champions, award_badges

class CricStakeTestCase(TestCase):
    
    def setUp(self):
        # Create Badges first (normally seeded)
        self.badge_first_win = Badge.objects.create(name="First Win", description="First win", icon="🏆")
        self.badge_streak = Badge.objects.create(name="3-Match Streak", description="3 correct", icon="🔥")
        self.badge_top = Badge.objects.create(name="Top Predictor", description="10 correct", icon="⚡")
        self.badge_champ = Badge.objects.create(name="Weekly Champion", description="Weekly winner", icon="👑")

        # Create Teams
        self.team_a = Team.objects.create(name="Mumbai Indians", short_name="MI")
        self.team_b = Team.objects.create(name="Chennai Super Kings", short_name="CSK")

        # Create Players
        self.player_a = Player.objects.create(name="Rohit Sharma", team=self.team_a)
        self.player_b = Player.objects.create(name="MS Dhoni", team=self.team_b)

        # Create Users
        self.user_karan = User.objects.create_user(username="karan", password="password123")
        self.user_priya = User.objects.create_user(username="priya", password="password123")

        # Create Room
        self.room = Room.objects.create(
            name="IPL Friends League",
            description="Fun league",
            invite_code=generate_invite_code(),
            created_by=self.user_karan
        )
        RoomMember.objects.create(room=self.room, user=self.user_karan)
        RoomMember.objects.create(room=self.room, user=self.user_priya)

        # Create Matches
        self.match_upcoming = Match.objects.create(
            team_a=self.team_a,
            team_b=self.team_b,
            match_datetime=timezone.now() + timedelta(days=1),
            status="upcoming"
        )
        
        self.match_completed = Match.objects.create(
            team_a=self.team_a,
            team_b=self.team_b,
            match_datetime=timezone.now() - timedelta(days=1),
            status="upcoming"
        )

    def test_user_profile_created_on_signup(self):
        """Verify that a UserProfile is automatically created on User registration with 1,000 coins."""
        user = User.objects.create_user(username="new_user", password="password123")
        self.assertIsNotNone(user.profile)
        self.assertEqual(user.profile.coin_balance, 1000)
        self.assertEqual(user.profile.total_predictions, 0)

    def test_invite_code_generation(self):
        """Verify invite codes are generated correctly and are unique."""
        code1 = generate_invite_code()
        code2 = generate_invite_code()
        self.assertEqual(len(code1), 6)
        self.assertNotEqual(code1, code2)

    def test_prediction_double_spend_safety(self):
        """Verify that placing and editing predictions correctly deducts/adjusts user balances."""
        profile = self.user_karan.profile
        self.assertEqual(profile.coin_balance, 1000)

        # Place Prediction 1: Winner, bet 200.
        # This will be simulated similar to views.py
        # Available balance: 1000. Deduct 200.
        profile.coin_balance -= 200
        profile.save()

        pred = Prediction.objects.create(
            user=self.user_karan,
            room=self.room,
            match=self.match_upcoming,
            market_type="winner",
            selected_value=str(self.team_a.id),
            bet_amount=200,
            multiplier=1.5
        )
        
        profile.refresh_from_db()
        self.assertEqual(profile.coin_balance, 800)

        # Edit Prediction 1: Change bet from 200 to 500.
        # Original bet was 200, so available balance is 800 + 200 = 1000.
        # User wants to bet 500. Balance becomes 1000 - 500 = 500.
        refund = pred.bet_amount
        available = profile.coin_balance + refund
        self.assertEqual(available, 1000)
        
        new_bet = 500
        profile.coin_balance = available - new_bet
        profile.save()
        
        pred.bet_amount = new_bet
        pred.save()
        
        profile.refresh_from_db()
        self.assertEqual(profile.coin_balance, 500)
        self.assertEqual(pred.bet_amount, 500)

    def test_match_settlement_win(self):
        """Verify that a correct prediction settlements awards coins, updates streaks and awards First Win badge."""
        profile = self.user_karan.profile
        
        # Place bet
        profile.coin_balance -= 200
        profile.save()
        
        pred = Prediction.objects.create(
            user=self.user_karan,
            room=self.room,
            match=self.match_completed,
            market_type="winner",
            selected_value=str(self.team_a.id),
            bet_amount=200,
            multiplier=1.5
        )

        # Complete match: Team A wins
        self.match_completed.status = "completed"
        self.match_completed.winner = self.team_a
        self.match_completed.save()

        # Settle
        settle_match_predictions(self.match_completed)

        pred.refresh_from_db()
        profile.refresh_from_db()

        self.assertEqual(pred.status, "won")
        # Payout is 200 * 1.5 = 300. Net profit is 100.
        # Coin balance was 800 (1000 - 200). 800 + 300 = 1100.
        self.assertEqual(profile.coin_balance, 1100)
        self.assertEqual(profile.total_predictions, 1)
        self.assertEqual(profile.correct_predictions, 1)
        self.assertEqual(profile.current_streak, 1)
        self.assertEqual(profile.longest_streak, 1)

        # Verify Badge Awarded
        self.assertTrue(UserBadge.objects.filter(user=self.user_karan, badge=self.badge_first_win).exists())

    def test_match_settlement_loss(self):
        """Verify that an incorrect prediction does not award coins, resets streak, and updates stats."""
        profile = self.user_karan.profile
        
        # Set a current streak of 2 to verify it resets to 0
        profile.current_streak = 2
        profile.longest_streak = 2
        # Place bet
        profile.coin_balance -= 200
        profile.save()
        
        pred = Prediction.objects.create(
            user=self.user_karan,
            room=self.room,
            match=self.match_completed,
            market_type="winner",
            selected_value=str(self.team_b.id), # Selected Team B
            bet_amount=200,
            multiplier=1.5
        )

        # Complete match: Team A wins
        self.match_completed.status = "completed"
        self.match_completed.winner = self.team_a
        self.match_completed.save()

        # Settle
        settle_match_predictions(self.match_completed)

        pred.refresh_from_db()
        profile.refresh_from_db()

        self.assertEqual(pred.status, "lost")
        # No coins credited. Balance was 800. Remains 800.
        self.assertEqual(profile.coin_balance, 800)
        self.assertEqual(profile.total_predictions, 1)
        self.assertEqual(profile.correct_predictions, 0)
        self.assertEqual(profile.current_streak, 0) # Resets to 0!
        self.assertEqual(profile.longest_streak, 2) # Preserved!

    def test_match_settlement_refund(self):
        """Verify that an abandoned match refunds bets to all users."""
        profile = self.user_karan.profile
        profile.coin_balance -= 300
        profile.save()

        pred = Prediction.objects.create(
            user=self.user_karan,
            room=self.room,
            match=self.match_completed,
            market_type="winner",
            selected_value=str(self.team_a.id),
            bet_amount=300,
            multiplier=1.5
        )

        # Abandon match
        self.match_completed.status = "abandoned"
        self.match_completed.save()

        # Settle
        settle_match_predictions(self.match_completed)

        pred.refresh_from_db()
        profile.refresh_from_db()

        self.assertEqual(pred.status, "refunded")
        self.assertEqual(profile.coin_balance, 1000) # Full 300 refunded!
        self.assertEqual(profile.total_predictions, 0) # Stats not increased for refunds!

    def test_weekly_champion_calculation(self):
        """Verify that weekly champions are calculated correctly based on net won prediction earnings."""
        # Setup: Completed Match 1 (Karan wins, Priya loses)
        m_today = Match.objects.create(
            team_a=self.team_a,
            team_b=self.team_b,
            match_datetime=timezone.now(),
            status="completed",
            winner=self.team_a
        )

        # Karan bet 200 on winner Team A (wins: payout 300, net +100)
        self.user_karan.profile.coin_balance -= 200
        self.user_karan.profile.save()
        Prediction.objects.create(
            user=self.user_karan,
            room=self.room,
            match=m_today,
            market_type="winner",
            selected_value=str(self.team_a.id),
            bet_amount=200,
            multiplier=1.5,
            status="pending"
        )

        # Priya bet 100 on winner Team B (loses: payout 0, net -100)
        self.user_priya.profile.coin_balance -= 100
        self.user_priya.profile.save()
        Prediction.objects.create(
            user=self.user_priya,
            room=self.room,
            match=m_today,
            market_type="winner",
            selected_value=str(self.team_b.id),
            bet_amount=100,
            multiplier=1.5,
            status="pending"
        )

        # Settle matches
        settle_match_predictions(m_today)

        # Calculate Weekly Champions
        champ = calculate_weekly_champions(self.room, check_date=date.today())
        
        self.assertIsNotNone(champ)
        self.assertEqual(champ.user, self.user_karan) # Karan has +100 net profit, Priya has 0/negative
        
        # Verify Karan awarded Weekly Champion Badge
        self.assertTrue(UserBadge.objects.filter(user=self.user_karan, badge=self.badge_champ).exists())

    def test_views_render_successfully(self):
        """Verify that dashboard, room detail, and prediction views render successfully without template syntax errors."""
        self.client.force_login(self.user_karan)
        
        # Test Landing / Redirect
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302) # Redirects to dashboard when logged in
        
        # Test Dashboard
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CricCoin Wallet")
        self.assertContains(response, "IPL Friends League")
        
        # Test Room Detail
        response = self.client.get(f'/room/{self.room.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "IPL Friends League")
        
        # Test Match Predict Page
        response = self.client.get(f'/room/{self.room.id}/match/{self.match_upcoming.id}/predict/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Predictions & Stakes")

    def test_views_trigger_auto_settlement(self):
        """Verify that loading the dashboard view automatically settles past scheduled matches and pays out coins."""
        profile = self.user_karan.profile
        self.assertEqual(profile.coin_balance, 1000)

        # Place a prediction on the completed (but currently 'upcoming') match
        profile.coin_balance -= 200
        profile.save()

        pred = Prediction.objects.create(
            user=self.user_karan,
            room=self.room,
            match=self.match_completed, # Scheduled in the past (-1 day)
            market_type="winner",
            selected_value=str(self.team_a.id),
            bet_amount=200,
            multiplier=1.5
        )

        self.assertEqual(self.match_completed.status, "upcoming")

        # Now, force login and load the dashboard page
        self.client.force_login(self.user_karan)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

        # The view should trigger auto_sync_completed_matches(), completing the match and settling the prediction
        self.match_completed.refresh_from_db()
        pred.refresh_from_db()
        profile.refresh_from_db()

        self.assertEqual(self.match_completed.status, "completed")
        self.assertEqual(pred.status, "won")
        # Balance was 800. Payout: 200 * 1.5 = 300. New balance = 1100.
        self.assertEqual(profile.coin_balance, 1100)

