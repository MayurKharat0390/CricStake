from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from datetime import date

from .models import UserProfile, Room, RoomMember, Team, Player, Match, Prediction, Badge, UserBadge, WeeklyChampion
from .utils import generate_invite_code, award_badges, auto_sync_completed_matches

# 1. Landing View
def landing_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')


# 2. Registration View
def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')
        
        if not username or not email or not password:
            messages.error(request, "All fields are required.")
            return render(request, 'register.html')
            
        if password != password_confirm:
            messages.error(request, "Passwords do not match.")
            return render(request, 'register.html')
            
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username is already taken.")
            return render(request, 'register.html')
            
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email is already registered.")
            return render(request, 'register.html')
            
        # Create user
        user = User.objects.create_user(username=username, email=email, password=password)
        login(request, user)
        messages.success(request, f"Welcome to CricStake, {username}! You've been credited 1,000 CricCoins.")
        return redirect('dashboard')
        
    return render(request, 'register.html')


# 3. Login View
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {username}!")
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid username or password.")
            
    return render(request, 'login.html')


# 4. Logout View
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('landing')


# 5. Dashboard View
@login_required
def dashboard_view(request):
    auto_sync_completed_matches()
    profile = request.user.profile
    # Refresh to make sure balance is current
    profile.refresh_from_db()
    
    # Get rooms joined by user
    room_memberships = RoomMember.objects.filter(user=request.user).select_related('room')
    rooms = [m.room for m in room_memberships]
    
    # Active predictions
    active_predictions = Prediction.objects.filter(
        user=request.user, 
        status='pending'
    ).select_related('match', 'match__team_a', 'match__team_b', 'room')
    
    return render(request, 'dashboard.html', {
        'profile': profile,
        'rooms': rooms,
        'active_predictions': active_predictions,
    })


# 6. Create Room
@login_required
def room_create_view(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        
        allow_winner = request.POST.get('allow_winner_market') == 'true'
        allow_toss = request.POST.get('allow_toss_market') == 'true'
        allow_pom = request.POST.get('allow_pom_market') == 'true'
        allow_batter = request.POST.get('allow_batter_market') == 'true'
        allow_bowler = request.POST.get('allow_bowler_market') == 'true'
        
        if not name:
            messages.error(request, "Room name is required.")
            return render(request, 'room_create.html')
            
        if not (allow_winner or allow_toss or allow_pom or allow_batter or allow_bowler):
            messages.error(request, "You must enable at least one prediction market.")
            return render(request, 'room_create.html')
            
        invite_code = generate_invite_code()
        
        with transaction.atomic():
            room = Room.objects.create(
                name=name,
                description=description,
                invite_code=invite_code,
                created_by=request.user,
                allow_winner_market=allow_winner,
                allow_toss_market=allow_toss,
                allow_pom_market=allow_pom,
                allow_batter_market=allow_batter,
                allow_bowler_market=allow_bowler
            )
            # Add creator as member
            RoomMember.objects.create(room=room, user=request.user)
            
        messages.success(request, f"Room '{name}' created successfully! Share the invite code: {invite_code}")
        return redirect('room_detail', room_id=room.id)
        
    return render(request, 'room_create.html')


# 7. Join Room
@login_required
def room_join_view(request):
    if request.method == 'POST':
        invite_code = request.POST.get('invite_code', '').strip().upper()
        
        if not invite_code:
            messages.error(request, "Invite code is required.")
            return render(request, 'room_join.html')
            
        try:
            room = Room.objects.get(invite_code=invite_code)
        except Room.DoesNotExist:
            messages.error(request, "Invalid invite code. Room not found.")
            return render(request, 'room_join.html')
            
        # Check if already a member
        if RoomMember.objects.filter(room=room, user=request.user).exists():
            messages.info(request, f"You are already a member of '{room.name}'.")
            return redirect('room_detail', room_id=room.id)
            
        from django.urls import reverse
        RoomMember.objects.create(room=room, user=request.user)
        messages.success(request, f"Successfully joined '{room.name}'!")
        return redirect(f"{reverse('room_detail', args=[room.id])}?joined=true")
        
    return render(request, 'room_join.html')


# 8. Room Detail
@login_required
def room_detail_view(request, room_id):
    auto_sync_completed_matches()
    room = get_object_or_404(Room, id=room_id)
    
    # Security: check membership
    if not RoomMember.objects.filter(room=room, user=request.user).exists():
        messages.error(request, "You are not a member of this room.")
        return redirect('dashboard')
        
    # Leaderboard (members ordered by coin balance)
    members = RoomMember.objects.filter(room=room).select_related('user', 'user__profile')
    leaderboard = sorted(members, key=lambda m: m.user.profile.coin_balance, reverse=True)
    
    # Matches
    upcoming_matches = Match.objects.filter(status='upcoming').order_by('match_datetime')
    completed_matches = Match.objects.filter(status__in=['completed', 'abandoned']).order_by('-match_datetime')
    
    # Weekly champions
    weekly_champions = WeeklyChampion.objects.filter(room=room).select_related('user').order_by('-week_start')
    
    # Attach predictions made by request.user for upcoming matches in this room
    user_predictions = Prediction.objects.filter(
        user=request.user,
        room=room,
        match__status='upcoming'
    ).values_list('match_id', flat=True)
    
    # Make user_predictions a set for O(1) lookups in template
    predicted_match_ids = set(user_predictions)
    
    return render(request, 'room_detail.html', {
        'room': room,
        'leaderboard': leaderboard,
        'upcoming_matches': upcoming_matches,
        'completed_matches': completed_matches,
        'weekly_champions': weekly_champions,
        'predicted_match_ids': predicted_match_ids,
    })


# 9. Match Prediction (Place & Review)
@login_required
def match_predict_view(request, room_id, match_id):
    auto_sync_completed_matches()
    room = get_object_or_404(Room, id=room_id)
    match = get_object_or_404(Match, id=match_id)
    
    # Security: check membership
    if not RoomMember.objects.filter(room=room, user=request.user).exists():
        messages.error(request, "You are not a member of this room.")
        return redirect('dashboard')
        
    # Get players & teams for options
    team_a = match.team_a
    team_b = match.team_b
    players_a = Player.objects.filter(team=team_a).order_by('name')
    players_b = Player.objects.filter(team=team_b).order_by('name')
    all_players = players_a | players_b
    
    # Build active multipliers list dynamically based on room settings
    market_multipliers = {}
    if room.allow_winner_market:
        market_multipliers['winner'] = 1.5
    if room.allow_toss_market:
        market_multipliers['toss'] = 2.0
    if room.allow_pom_market:
        market_multipliers['pom'] = 4.0
    if room.allow_batter_market:
        market_multipliers['top_batter'] = 3.0
    if room.allow_bowler_market:
        market_multipliers['top_bowler'] = 3.0
        
    if not market_multipliers:
        # Fallback if none are set
        market_multipliers = {
            'winner': 1.5,
            'toss': 2.0,
            'pom': 4.0,
            'top_batter': 3.0,
            'top_bowler': 3.0,
        }
    
    profile = request.user.profile
    profile.refresh_from_db()
    
    # If not locked: Process prediction placement/editing
    if not match.is_locked:
        existing_predictions = Prediction.objects.filter(
            user=request.user,
            room=room,
            match=match
        )
        # Create map of market_type -> prediction for template
        pred_map = {p.market_type: p for p in existing_predictions}
        
        if request.method == 'POST':
            market_type = request.POST.get('market_type')
            selected_value = request.POST.get('selected_value')
            bet_amount_str = request.POST.get('bet_amount', '0')
            confidence_level = request.POST.get('confidence_level', None)
            
            if not market_type or not selected_value:
                messages.error(request, "Invalid prediction selection.")
                return redirect('match_predict', room_id=room.id, match_id=match.id)
                
            if market_type not in market_multipliers:
                messages.error(request, "This prediction market is disabled in this room.")
                return redirect('match_predict', room_id=room.id, match_id=match.id)
                
            try:
                bet_amount = int(bet_amount_str)
                if bet_amount <= 0:
                    raise ValueError()
            except ValueError:
                messages.error(request, "Bet amount must be a positive integer.")
                return redirect('match_predict', room_id=room.id, match_id=match.id)
                
            # Double-spend safe transaction logic
            with transaction.atomic():
                # Refresh profile inside transaction
                prof = UserProfile.objects.select_for_update().get(id=profile.id)
                
                # Fetch existing prediction if any
                existing_pred = Prediction.objects.filter(
                    user=request.user,
                    room=room,
                    match=match,
                    market_type=market_type
                ).first()
                
                # Available balance calculation
                refund_amount = existing_pred.bet_amount if existing_pred else 0
                available_balance = prof.coin_balance + refund_amount
                
                if bet_amount > available_balance:
                    messages.error(request, f"Insufficient coins. Max bet available: {available_balance} CricCoins.")
                    return redirect('match_predict', room_id=room.id, match_id=match.id)
                    
                # Deduct difference from profile balance
                prof.coin_balance = available_balance - bet_amount
                prof.save()
                
                # Save prediction
                multiplier = market_multipliers.get(market_type, 1.0)
                if existing_pred:
                    existing_pred.selected_value = selected_value
                    existing_pred.bet_amount = bet_amount
                    existing_pred.confidence_level = confidence_level
                    existing_pred.multiplier = multiplier
                    existing_pred.save()
                else:
                    Prediction.objects.create(
                        user=request.user,
                        room=room,
                        match=match,
                        market_type=market_type,
                        selected_value=selected_value,
                        bet_amount=bet_amount,
                        confidence_level=confidence_level,
                        multiplier=multiplier
                    )
                    
            messages.success(request, f"Prediction for {market_type.replace('_', ' ').title()} placed successfully!")
            return redirect('match_predict', room_id=room.id, match_id=match.id)
            
        return render(request, 'match_predict.html', {
            'room': room,
            'match': match,
            'team_a': team_a,
            'team_b': team_b,
            'players_a': players_a,
            'players_b': players_b,
            'all_players': all_players,
            'pred_map': pred_map,
            'profile': profile,
            'multipliers': market_multipliers,
        })
        
    else:
        # Match IS locked: Reveal comparison matrix
        # Fetch all predictions for this room and match
        all_room_preds = Prediction.objects.filter(
            room=room,
            match=match
        ).select_related('user', 'user__profile')
        
        # Build active markets list for dynamic columns in template
        active_markets = []
        if room.allow_winner_market:
            active_markets.append({'code': 'winner', 'name': 'Match Winner', 'mult': '1.5x'})
        if room.allow_toss_market:
            active_markets.append({'code': 'toss', 'name': 'Toss Winner', 'mult': '2.0x'})
        if room.allow_pom_market:
            active_markets.append({'code': 'pom', 'name': 'POM', 'mult': '4.0x'})
        if room.allow_batter_market:
            active_markets.append({'code': 'top_batter', 'name': 'Top Batter', 'mult': '3.0x'})
        if room.allow_bowler_market:
            active_markets.append({'code': 'top_bowler', 'name': 'Top Bowler', 'mult': '3.0x'})
            
        if not active_markets:
            active_markets = [
                {'code': 'winner', 'name': 'Match Winner', 'mult': '1.5x'},
                {'code': 'toss', 'name': 'Toss Winner', 'mult': '2.0x'},
                {'code': 'pom', 'name': 'POM', 'mult': '4.0x'},
                {'code': 'top_batter', 'name': 'Top Batter', 'mult': '3.0x'},
                {'code': 'top_bowler', 'name': 'Top Bowler', 'mult': '3.0x'},
            ]
            
        # Structure by user: user -> list of predictions
        user_pred_matrix = {}
        room_members = RoomMember.objects.filter(room=room).select_related('user', 'user__profile')
        for rm in room_members:
            user_pred_matrix[rm.user] = {
                'winner': None,
                'toss': None,
                'pom': None,
                'top_batter': None,
                'top_bowler': None,
            }
            
        for pred in all_room_preds:
            if pred.user in user_pred_matrix:
                user_pred_matrix[pred.user][pred.market_type] = pred
                
        # Resolve names of selected values to render nicely
        # (Since they are IDs, we create a map of IDs to names)
        resolved_names = {}
        for t in [team_a, team_b]:
            resolved_names[str(t.id)] = t.short_name
        for p in all_players:
            resolved_names[str(p.id)] = p.name
            
        return render(request, 'match_predict.html', {
            'room': room,
            'match': match,
            'user_pred_matrix': user_pred_matrix,
            'resolved_names': resolved_names,
            'profile': profile,
            'active_markets': active_markets,
        })


# 10. Profile View (Own or Friend's)
def profile_view(request, username=None):
    auto_sync_completed_matches()
    if username:
        user = get_object_or_404(User, username=username)
    else:
        if not request.user.is_authenticated:
            return redirect('login')
        user = request.user
        
    profile = user.profile
    profile.refresh_from_db()
    
    # Badges earned
    earned_badges = UserBadge.objects.filter(user=user).select_related('badge')
    
    # Recent settled predictions
    settled_predictions = Prediction.objects.filter(
        user=user,
        status__in=['won', 'lost', 'refunded']
    ).select_related('match', 'match__team_a', 'match__team_b', 'room').order_by('-created_at')[:15]
    
    is_own_profile = (request.user.is_authenticated and user == request.user)
    
    return render(request, 'profile.html', {
        'profile_user': user,
        'profile': profile,
        'earned_badges': earned_badges,
        'settled_predictions': settled_predictions,
        'is_own_profile': is_own_profile,
    })


# 11. Room Settings View
@login_required
def room_settings_view(request, room_id):
    from django.urls import reverse
    room = get_object_or_404(Room, id=room_id)
    
    # Secure validation: Check authorization (Only room creator is the admin)
    if request.user != room.created_by:
        messages.error(request, "Only the room admin/creator can manage room settings.")
        return redirect('room_detail', room_id=room.id)
        
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        
        allow_winner = request.POST.get('allow_winner_market') == 'true'
        allow_toss = request.POST.get('allow_toss_market') == 'true'
        allow_pom = request.POST.get('allow_pom_market') == 'true'
        allow_batter = request.POST.get('allow_batter_market') == 'true'
        allow_bowler = request.POST.get('allow_bowler_market') == 'true'
        
        if not name:
            messages.error(request, "Room name is required.")
            return render(request, 'room_settings.html', {'room': room})
            
        if not (allow_winner or allow_toss or allow_pom or allow_batter or allow_bowler):
            messages.error(request, "You must enable at least one prediction market.")
            return render(request, 'room_settings.html', {'room': room})
            
        # Update room
        room.name = name
        room.description = description
        room.allow_winner_market = allow_winner
        room.allow_toss_market = allow_toss
        room.allow_pom_market = allow_pom
        room.allow_batter_market = allow_batter
        room.allow_bowler_market = allow_bowler
        room.save()
        
        messages.success(request, f"Room '{name}' settings updated successfully!")
        return redirect('room_detail', room_id=room.id)
        
    return render(request, 'room_settings.html', {'room': room})

# 12. Leave Room View
@login_required
def room_leave_view(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    # Verify membership
    membership = RoomMember.objects.filter(room=room, user=request.user).first()
    if not membership:
        messages.error(request, "You are not a member of this room.")
        return redirect('dashboard')
    # Prevent admin from leaving (optional)
    if request.user == room.created_by:
        messages.error(request, "Room creator cannot leave the room. Transfer ownership or delete the room.")
        return redirect('room_detail', room_id=room.id)
    membership.delete()
    messages.success(request, f"You have left the room '{room.name}'.")
    return redirect('dashboard')

# 13. Kick Member View (Admin only)
@login_required
def room_kick_member_view(request, room_id, user_id):
    room = get_object_or_404(Room, id=room_id)
    if request.user != room.created_by:
        messages.error(request, "Only the room admin can kick members.")
        return redirect('room_detail', room_id=room.id)
    member = get_object_or_404(RoomMember, room=room, user_id=user_id)
    if member.user == room.created_by:
        messages.error(request, "Cannot kick the room creator.")
        return redirect('room_detail', room_id=room.id)
    member.delete()
    messages.success(request, f"User '{member.user.username}' has been removed from the room.")
    return redirect('room_detail', room_id=room.id)

# 14. Room History View (Settled Predictions)
@login_required
def room_history_view(request, room_id):
    auto_sync_completed_matches()
    room = get_object_or_404(Room, id=room_id)
    if not RoomMember.objects.filter(room=room, user=request.user).exists():
        messages.error(request, "You are not a member of this room.")
        return redirect('dashboard')
    
    settled_predictions = Prediction.objects.filter(
        room=room,
        status__in=['won', 'lost', 'refunded']
    ).select_related('user', 'match', 'match__team_a', 'match__team_b').order_by('-created_at')

    # Resolve IDs to readable names
    teams = Team.objects.all()
    players = Player.objects.all()
    resolved_names = {}
    for t in teams:
        resolved_names[str(t.id)] = t.short_name
    for p in players:
        resolved_names[str(p.id)] = p.name

    return render(request, 'room_history.html', {
        'room': room,
        'settled_predictions': settled_predictions,
        'resolved_names': resolved_names,
    })
