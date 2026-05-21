from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal

# 1. UserProfile Model
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    coin_balance = models.PositiveIntegerField(default=1000)
    total_predictions = models.PositiveIntegerField(default=0)
    correct_predictions = models.PositiveIntegerField(default=0)
    current_streak = models.PositiveIntegerField(default=0)
    longest_streak = models.PositiveIntegerField(default=0)

    @property
    def accuracy_percentage(self):
        if self.total_predictions == 0:
            return 0.0
        return round((self.correct_predictions / self.total_predictions) * 100, 1)

    def __str__(self):
        return f"{self.user.username}'s Profile - {self.coin_balance} Coins"


# Auto-create UserProfile on User signup
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # Safe check in case profile wasn't created
    if hasattr(instance, 'profile'):
        instance.profile.save()
    else:
        UserProfile.objects.create(user=instance)


# 2. Room Model
class Room(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    invite_code = models.CharField(max_length=10, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_rooms')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Market type toggles (decided by Admin/Creator)
    allow_winner_market = models.BooleanField(default=True, verbose_name="Allow Match Winner prediction")
    allow_toss_market = models.BooleanField(default=True, verbose_name="Allow Toss Winner prediction")
    allow_pom_market = models.BooleanField(default=True, verbose_name="Allow Player of the Match prediction")
    allow_batter_market = models.BooleanField(default=True, verbose_name="Allow Top Batter prediction")
    allow_bowler_market = models.BooleanField(default=True, verbose_name="Allow Top Bowler prediction")

    def __str__(self):
        return self.name


# 3. RoomMember Model
class RoomMember(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='room_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('room', 'user')

    def __str__(self):
        return f"{self.user.username} in {self.room.name}"


# 4. Team Model
class Team(models.Model):
    name = models.CharField(max_length=100)
    short_name = models.CharField(max_length=10)
    logo_svg = models.TextField(blank=True, null=True, help_text="Inline raw SVG tag for rendering the logo.")

    def __str__(self):
        return f"{self.name} ({self.short_name})"


# 5. Player Model
class Player(models.Model):
    name = models.CharField(max_length=100)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='players')

    def __str__(self):
        return f"{self.name} ({self.team.short_name})"


# 6. Match Model
class Match(models.Model):
    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('live', 'Live'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ]

    team_a = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='home_matches')
    team_b = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='away_matches')
    match_datetime = models.DateTimeField()
    venue = models.CharField(max_length=200, blank=True, help_text='Match venue or city')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='upcoming')
    
    toss_winner = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='matches_toss_won')
    winner = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='matches_won')
    player_of_match = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, blank=True, related_name='matches_pom')
    top_batter = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, blank=True, related_name='matches_top_batter')
    top_bowler = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, blank=True, related_name='matches_top_bowler')
    api_match_id = models.CharField(max_length=50, blank=True, null=True, help_text="CricketData.org Match ID for automatic syncing")

    @property
    def is_locked(self):
        return timezone.now() >= self.match_datetime or self.status != 'upcoming'

    def __str__(self):
        return f"{self.team_a.short_name} vs {self.team_b.short_name} on {self.match_datetime.strftime('%b %d, %I:%M %p')}"


# 7. Prediction Model
class Prediction(models.Model):
    MARKET_CHOICES = [
        ('winner', 'Match Winner'),
        ('toss', 'Toss Winner'),
        ('pom', 'Player of the Match'),
        ('top_batter', 'Top Batter'),
        ('top_bowler', 'Top Bowler'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('won', 'Won'),
        ('lost', 'Lost'),
        ('refunded', 'Refunded'),
    ]

    CONFIDENCE_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='predictions')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='predictions')
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='predictions')
    market_type = models.CharField(max_length=20, choices=MARKET_CHOICES)
    selected_value = models.CharField(max_length=100, help_text="ID of Team or Player selected (e.g., 'team_5' or 'player_23')")
    bet_amount = models.PositiveIntegerField()
    confidence_level = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, blank=True, null=True)
    multiplier = models.DecimalField(max_digits=4, decimal_places=1, default=1.0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    coins_change = models.IntegerField(default=0, help_text="Net change in coins for the user profile.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'room', 'match', 'market_type')

    def __str__(self):
        return f"{self.user.username} - {self.room.name} - {self.match.team_a.short_name} vs {self.match.team_b.short_name} ({self.market_type})"


# 8. Badge Model
class Badge(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    icon = models.CharField(max_length=50, help_text="Emoji or Tailwind CSS/Lucide icon name (e.g., '🏆', '🔥')")

    def __str__(self):
        return self.name


# 9. UserBadge Model
class UserBadge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='badges')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name='earners')
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'badge')

    def __str__(self):
        return f"{self.user.username} earned {self.badge.name}"


# 10. WeeklyChampion Model
class WeeklyChampion(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='weekly_champions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='weekly_championships')
    week_start = models.DateField(help_text="Monday date of the champion's week.")

    class Meta:
        unique_together = ('room', 'week_start')

    def __str__(self):
        return f"Week {self.week_start}: {self.user.username} in {self.room.name}"
