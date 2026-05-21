from django.contrib import admin
from django.contrib import messages
from .models import UserProfile, Room, RoomMember, Team, Player, Match, Prediction, Badge, UserBadge, WeeklyChampion
from .utils import settle_match_predictions, calculate_weekly_champions

# 1. Custom Admin Actions for Match Settle
@admin.action(description="Settle predictions for selected matches")
def settle_predictions_action(modeladmin, request, queryset):
    settled_count = 0
    ignored_count = 0
    for match in queryset:
        if match.status in ['completed', 'abandoned']:
            settle_match_predictions(match)
            settled_count += 1
        else:
            ignored_count += 1
            
    if settled_count > 0:
        modeladmin.message_user(
            request, 
            f"Successfully settled predictions for {settled_count} matches.", 
            messages.SUCCESS
        )
    if ignored_count > 0:
        modeladmin.message_user(
            request, 
            f"{ignored_count} matches were ignored because they are not 'Completed' or 'Abandoned'.", 
            messages.WARNING
        )

@admin.action(description="Calculate weekly champions for selected rooms")
def calculate_weekly_champions_action(modeladmin, request, queryset):
    calculated_rooms = []
    for room in queryset:
        champ = calculate_weekly_champions(room)
        if champ:
            calculated_rooms.append(f"{room.name} (Winner: {champ.user.username})")
        else:
            calculated_rooms.append(f"{room.name} (No Winner - no positive net earnings)")
            
    modeladmin.message_user(
        request,
        f"Weekly champions calculated for rooms: {', '.join(calculated_rooms)}",
        messages.SUCCESS
    )


# 2. Registering Model Admins
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'coin_balance', 'total_predictions', 'correct_predictions', 'current_streak', 'longest_streak', 'accuracy_percentage')
    search_fields = ('user__username', 'user__email')
    list_filter = ('current_streak', 'longest_streak')
    ordering = ('-coin_balance',)


class RoomMemberInline(admin.TabularInline):
    model = RoomMember
    extra = 1

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'invite_code', 'created_by', 'created_at')
    search_fields = ('name', 'invite_code', 'created_by__username')
    inlines = [RoomMemberInline]
    actions = [calculate_weekly_champions_action]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'short_name')
    search_fields = ('name', 'short_name')


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('name', 'team')
    search_fields = ('name', 'team__name', 'team__short_name')
    list_filter = ('team',)


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'match_datetime', 'status', 'winner', 'player_of_match', 'is_locked')
    list_filter = ('status', 'match_datetime')
    search_fields = ('team_a__name', 'team_b__name', 'team_a__short_name', 'team_b__short_name')
    actions = [settle_predictions_action]
    
    # Organize fields in detail view
    fieldsets = (
        ('Match Info', {
            'fields': ('team_a', 'team_b', 'match_datetime', 'status')
        }),
        ('Results (Enter when Match is Completed)', {
            'fields': ('toss_winner', 'winner', 'player_of_match', 'top_batter', 'top_bowler')
        }),
    )


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = ('user', 'room', 'match', 'market_type', 'selected_value', 'bet_amount', 'multiplier', 'status', 'coins_change')
    list_filter = ('status', 'market_type', 'confidence_level')
    search_fields = ('user__username', 'room__name', 'selected_value')
    readonly_fields = ('created_at',)


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'icon')


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ('user', 'badge', 'earned_at')
    list_filter = ('badge', 'earned_at')
    search_fields = ('user__username', 'badge__name')


@admin.register(WeeklyChampion)
class WeeklyChampionAdmin(admin.ModelAdmin):
    list_display = ('room', 'user', 'week_start')
    list_filter = ('week_start', 'room')
    search_fields = ('user__username', 'room__name')
