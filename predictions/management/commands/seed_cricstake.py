import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, timedelta
from predictions.models import Team, Player, Match, Prediction, Badge, UserProfile, Room, RoomMember, WeeklyChampion
from predictions.utils import settle_match_predictions, calculate_weekly_champions

class Command(BaseCommand):
    help = "Seeds the CricStake database with all 10 real IPL teams, players, actual IPL 2026 matches, demo users, and predictions."

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting CricStake database seeding...")
        
        self.stdout.write("Cleaning up existing database records to prevent duplicates and outdated matches...")
        Prediction.objects.all().delete()
        Match.objects.all().delete()
        RoomMember.objects.all().delete()
        Room.objects.all().delete()
        WeeklyChampion.objects.all().delete()
        Player.objects.all().delete()
        Team.objects.all().delete()

        # 1. Create Superuser & Demo Users
        self.stdout.write("Creating users...")
        admin_user, created = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@cricstake.com", "is_staff": True, "is_superuser": True}
        )
        if created:
            admin_user.set_password("admin123")
            admin_user.save()
            self.stdout.write("Created superuser 'admin' (password: admin123)")
        else:
            self.stdout.write("Superuser 'admin' already exists.")

        demo_users_data = [
            ("karan", "karan@cricstake.com", "cricstake123"),
            ("priya", "priya@cricstake.com", "cricstake123"),
            ("rahul", "rahul@cricstake.com", "cricstake123"),
        ]
        users = {}
        for username, email, password in demo_users_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": email}
            )
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(f"Created demo user '{username}' (password: {password})")
            users[username] = user

        # Reset coin balances to default 1000 for seed repeatability
        for user in users.values():
            profile = user.profile
            profile.coin_balance = 1000
            profile.total_predictions = 0
            profile.correct_predictions = 0
            profile.current_streak = 0
            profile.longest_streak = 0
            profile.save()

        # 2. Create Badges
        self.stdout.write("Creating badges...")
        badges = {
            "First Win": Badge.objects.get_or_create(
                name="First Win",
                defaults={"description": "Awarded for your first correct prediction!", "icon": "🏆"}
            )[0],
            "3-Match Streak": Badge.objects.get_or_create(
                name="3-Match Streak",
                defaults={"description": "Awarded for getting 3 correct predictions in a row!", "icon": "🔥"}
            )[0],
            "Top Predictor": Badge.objects.get_or_create(
                name="Top Predictor",
                defaults={"description": "Awarded for reaching 10 correct predictions!", "icon": "⚡"}
            )[0],
            "Weekly Champion": Badge.objects.get_or_create(
                name="Weekly Champion",
                defaults={"description": "Awarded for dominating a room leaderboard as the Weekly Champion!", "icon": "👑"}
            )[0],
        }

        # 3. Create Teams with inline SVG Logos (Premium glassmorphic branding for all 10 IPL franchises!)
        self.stdout.write("Creating all 10 real IPL teams...")
        
        # 1. MI Logo SVG
        mi_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="w-12 h-12">
            <defs>
                <linearGradient id="miGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#004BA0"/>
                    <stop offset="100%" stop-color="#002D62"/>
                </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="45" fill="url(#miGrad)" stroke="#E5B80B" stroke-width="3"/>
            <path d="M50,20 C35,20 20,35 20,50 C20,60 25,68 32,73 L35,63 C31,60 28,55 28,50 C28,38 38,28 50,28 C62,28 72,38 72,50 C72,55 69,60 65,63 L68,73 C75,68 80,60 80,50 C80,35 65,20 50,20 Z" fill="#E5B80B"/>
            <path d="M50,35 C42,35 35,42 35,50 C35,55 37,59 41,62 L43,54 C42,53 41,51 41,50 C41,45 45,41 50,41 C55,41 59,45 59,50 C59,51 58,53 57,54 L59,62 C63,59 65,55 65,50 C65,42 58,35 50,35 Z" fill="#FFFFFF"/>
            <circle cx="50" cy="50" r="6" fill="#E5B80B"/>
        </svg>"""

        # 2. CSK Logo SVG
        csk_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="w-12 h-12">
            <defs>
                <linearGradient id="cskGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#FCD116"/>
                    <stop offset="100%" stop-color="#FF9933"/>
                </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="45" fill="url(#cskGrad)" stroke="#004BA0" stroke-width="3"/>
            <path d="M30,35 Q40,25 55,25 Q70,25 70,40 Q70,55 55,60 Q50,62 48,68 L42,65 Q45,55 45,50 Q32,50 30,35 Z" fill="#004BA0"/>
            <path d="M52,38 Q58,38 60,42 Q58,46 54,44 Q50,42 52,38 Z" fill="#FFFFFF"/>
            <path d="M35,65 Q48,65 52,78 Q50,82 45,80 Q43,72 35,65 Z" fill="#FF9933"/>
        </svg>"""

        # 3. RCB Logo SVG
        rcb_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="w-12 h-12">
            <defs>
                <linearGradient id="rcbGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#000000"/>
                    <stop offset="50%" stop-color="#1E1E1E"/>
                    <stop offset="100%" stop-color="#800000"/>
                </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="45" fill="url(#rcbGrad)" stroke="#E5B80B" stroke-width="3"/>
            <path d="M40,25 L60,25 L65,35 L35,35 Z" fill="#E5B80B"/>
            <path d="M43,38 L57,38 L60,52 L40,52 Z" fill="#D2143A"/>
            <path d="M45,56 L55,56 L57,75 L43,75 Z" fill="#E5B80B"/>
            <circle cx="50" cy="45" r="3" fill="#FFFFFF"/>
        </svg>"""

        # 4. KKR Logo SVG
        kkr_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="w-12 h-12">
            <defs>
                <linearGradient id="kkrGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#3D0C5A"/>
                    <stop offset="100%" stop-color="#210037"/>
                </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="45" fill="url(#kkrGrad)" stroke="#E5B80B" stroke-width="3"/>
            <path d="M30,30 L70,30 L65,65 L50,80 L35,65 Z" fill="#E5B80B" opacity="0.8"/>
            <path d="M38,38 L62,38 L58,60 L50,70 L42,60 Z" fill="#3D0C5A"/>
            <path d="M48,22 L52,22 L53,30 L47,30 Z" fill="#FFCC00"/>
            <path d="M42,42 L58,42 L50,55 Z" fill="#FFFFFF"/>
        </svg>"""

        # 5. SRH Logo SVG
        srh_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="w-12 h-12">
            <defs>
                <linearGradient id="srhGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#FF5400"/>
                    <stop offset="100%" stop-color="#1E1E1E"/>
                </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="45" fill="url(#srhGrad)" stroke="#FFD700" stroke-width="3"/>
            <circle cx="50" cy="50" r="16" fill="#FF5400" opacity="0.3"/>
            <path d="M50,15 L53,30 L65,22 L57,33 L72,33 L59,38 L72,48 L58,45 L65,58 L52,48 L50,65 L48,48 L35,58 L42,45 L28,48 L41,38 L28,33 L43,33 L35,22 L47,30 Z" fill="#FFD700"/>
            <path d="M25,70 Q50,55 75,70 L65,75 Q50,68 35,75 Z" fill="#FF5400"/>
        </svg>"""

        # 6. RR Logo SVG
        rr_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="w-12 h-12">
            <defs>
                <linearGradient id="rrGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#EA1E63"/>
                    <stop offset="100%" stop-color="#002D62"/>
                </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="45" fill="url(#rrGrad)" stroke="#FFD700" stroke-width="3"/>
            <path d="M30,70 L35,40 L45,55 L50,30 L55,55 L65,40 L70,70 Z" fill="#FFD700"/>
            <circle cx="35" cy="35" r="3" fill="#FFFFFF"/>
            <circle cx="50" cy="25" r="3" fill="#FFFFFF"/>
            <circle cx="65" cy="35" r="3" fill="#FFFFFF"/>
        </svg>"""

        # 7. LSG Logo SVG
        lsg_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="w-12 h-12">
            <defs>
                <linearGradient id="lsgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#0A2240"/>
                    <stop offset="100%" stop-color="#00A896"/>
                </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="45" fill="url(#lsgGrad)" stroke="#FF4D4D" stroke-width="3"/>
            <path d="M25,35 Q40,35 50,45 Q60,35 75,35 Q65,60 50,75 Q35,60 25,35 Z" fill="#FFFFFF" opacity="0.9"/>
            <path d="M30,38 Q42,48 50,65 Q58,48 70,38 Q60,52 50,58 Q40,52 30,38 Z" fill="#FF4D4D"/>
        </svg>"""

        # 8. DC Logo SVG
        dc_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="w-12 h-12">
            <defs>
                <linearGradient id="dcGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#0E4BB0"/>
                    <stop offset="100%" stop-color="#D50000"/>
                </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="45" fill="url(#dcGrad)" stroke="#FFFFFF" stroke-opacity="0.3" stroke-width="3"/>
            <path d="M30,35 L40,25 L50,30 L60,25 L70,35 L65,65 L50,78 L35,65 Z" fill="#FFFFFF" opacity="0.9"/>
            <path d="M42,45 C45,40 55,40 58,45 L50,55 Z" fill="#D50000"/>
        </svg>"""

        # 9. GT Logo SVG
        gt_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="w-12 h-12">
            <defs>
                <linearGradient id="gtGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#0B132B"/>
                    <stop offset="100%" stop-color="#1C2541"/>
                </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="45" fill="url(#gtGrad)" stroke="#E5B80B" stroke-width="3"/>
            <path d="M60,20 L30,52 L50,52 L40,80 L70,48 L50,48 Z" fill="#E5B80B"/>
        </svg>"""

        # 10. PBKS Logo SVG
        pbks_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" class="w-12 h-12">
            <defs>
                <linearGradient id="pbksGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#D50000"/>
                    <stop offset="100%" stop-color="#B0BEC5"/>
                </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="45" fill="url(#pbksGrad)" stroke="#FFFFFF" stroke-width="3"/>
            <path d="M30,45 Q40,30 50,40 Q60,30 70,45 L65,72 Q50,78 35,72 Z" fill="#FFFFFF"/>
            <path d="M38,48 Q42,42 50,48 Q58,42 62,48 Q55,56 50,62 Q45,56 38,48 Z" fill="#D50000"/>
        </svg>"""

        teams_data = [
            ("Mumbai Indians", "MI", mi_svg),
            ("Chennai Super Kings", "CSK", csk_svg),
            ("Royal Challengers Bengaluru", "RCB", rcb_svg),
            ("Kolkata Knight Riders", "KKR", kkr_svg),
            ("Sunrisers Hyderabad", "SRH", srh_svg),
            ("Rajasthan Royals", "RR", rr_svg),
            ("Lucknow Super Giants", "LSG", lsg_svg),
            ("Delhi Capitals", "DC", dc_svg),
            ("Gujarat Titans", "GT", gt_svg),
            ("Punjab Kings", "PBKS", pbks_svg),
        ]
        
        teams = {}
        for name, short, svg in teams_data:
            team, created = Team.objects.get_or_create(
                short_name=short,
                defaults={"name": name, "logo_svg": svg}
            )
            teams[short] = team
            self.stdout.write(f"Loaded Team {name} ({short})")

        # 4. Create Players
        self.stdout.write("Creating players...")
        players_data = {
            "MI": ["Rohit Sharma", "Hardik Pandya", "Jasprit Bumrah", "Suryakumar Yadav", "Ishan Kishan", "Corbin Bosch"],
            "CSK": ["MS Dhoni", "Ruturaj Gaikwad", "Ravindra Jadeja", "Matheesha Pathirana", "Shivam Dube"],
            "RCB": ["Virat Kohli", "Faf du Plessis", "Glenn Maxwell", "Mohammed Siraj", "Rajat Patidar"],
            "KKR": ["Ajinkya Rahane", "Shreyas Iyer", "Andre Russell", "Sunil Narine", "Rinku Singh", "Mitchell Starc"],
            "SRH": ["Pat Cummins", "Travis Head", "Abhishek Sharma", "Heinrich Klaasen", "Bhuvneshwar Kumar"],
            "RR": ["Sanju Samson", "Yashasvi Jaiswal", "Jos Buttler", "Yuzvendra Chahal", "Trent Boult", "Vaibhav Sooryavanshi"],
            "LSG": ["KL Rahul", "Nicholas Pooran", "Quinton de Kock", "Marcus Stoinis", "Ravi Bishnoi"],
            "DC": ["Rishabh Pant", "David Warner", "Axar Patel", "Kuldeep Yadav", "Jake Fraser-McGurk"],
            "GT": ["Shubman Gill", "Rashid Khan", "Sai Sudharsan", "David Miller", "Mohit Sharma"],
            "PBKS": ["Shikhar Dhawan", "Sam Curran", "Liam Livingstone", "Arshdeep Singh", "Shashank Singh"],
        }
        players = {}
        for short_name, p_list in players_data.items():
            team = teams[short_name]
            players[short_name] = []
            for p_name in p_list:
                player, created = Player.objects.get_or_create(
                    name=p_name,
                    team=team
                )
                players[short_name].append(player)
            self.stdout.write(f"Added {len(p_list)} players for {short_name}")

        # 5. Create Private Rooms and Members
        self.stdout.write("Creating private rooms...")
        room, created = Room.objects.get_or_create(
            name="IPL Kings League",
            defaults={
                "description": "The ultimate battleground for Cricket fans! Predict matches, earn coins, and gain the Crown.",
                "invite_code": "CRICST",
                "created_by": users["karan"]
            }
        )
        self.stdout.write(f"Created Room '{room.name}' (Invite Code: {room.invite_code})")

        # Add users as room members
        for user in users.values():
            RoomMember.objects.get_or_create(room=room, user=user)

        # 6. Create Matches (Exact IPL 2026 timetable from May 18 onwards!)
        self.stdout.write("Creating matches...")
        
        # Match 1: Completed (CSK vs SRH, played May 18, 2026 7:30 PM)
        m1 = Match.objects.create(
            team_a=teams["CSK"],
            team_b=teams["SRH"],
            match_datetime=timezone.make_aware(datetime(2026, 5, 18, 19, 30)),
            status="completed",
            toss_winner=teams["SRH"],
            winner=teams["SRH"],
            player_of_match=Player.objects.get(name="Travis Head"),
            top_batter=Player.objects.get(name="Travis Head"),
            top_bowler=Player.objects.get(name="Pat Cummins"),
            api_match_id="real-ipl-match-1"
        )
        self.stdout.write(f"Created completed match: {m1}")

        # Match 2: Completed (RR vs LSG, played May 19, 2026 7:30 PM)
        m2 = Match.objects.create(
            team_a=teams["RR"],
            team_b=teams["LSG"],
            match_datetime=timezone.make_aware(datetime(2026, 5, 19, 19, 30)),
            status="completed",
            toss_winner=teams["RR"],
            winner=teams["RR"],
            player_of_match=Player.objects.get(name="Vaibhav Sooryavanshi"),
            top_batter=Player.objects.get(name="Vaibhav Sooryavanshi"),
            top_bowler=Player.objects.get(name="Yuzvendra Chahal"),
            api_match_id="real-ipl-match-2"
        )
        self.stdout.write(f"Created completed match: {m2}")

        # Match 3: Live / Ongoing (KKR vs MI, May 20, 2026 7:30 PM)
        m3 = Match.objects.create(
            team_a=teams["KKR"],
            team_b=teams["MI"],
            match_datetime=timezone.make_aware(datetime(2026, 5, 20, 19, 30)),
            status="live",
            toss_winner=teams["KKR"],
            api_match_id="live-ipl-match-1"
        )
        self.stdout.write(f"Created live match: {m3}")

        # Match 4: Upcoming (GT vs CSK, May 21, 2026 7:30 PM)
        m4 = Match.objects.create(
            team_a=teams["GT"],
            team_b=teams["CSK"],
            match_datetime=timezone.make_aware(datetime(2026, 5, 21, 19, 30)),
            status="upcoming",
            api_match_id="live-ipl-match-2"
        )
        self.stdout.write(f"Created upcoming match: {m4}")

        # Match 5: Upcoming (SRH vs RCB, May 22, 2026 7:30 PM)
        m5 = Match.objects.create(
            team_a=teams["SRH"],
            team_b=teams["RCB"],
            match_datetime=timezone.make_aware(datetime(2026, 5, 22, 19, 30)),
            status="upcoming",
            api_match_id="live-ipl-match-3"
        )
        self.stdout.write(f"Created upcoming match: {m5}")

        # Match 6: Upcoming (LSG vs PBKS, May 23, 2026 7:30 PM)
        m6 = Match.objects.create(
            team_a=teams["LSG"],
            team_b=teams["PBKS"],
            match_datetime=timezone.make_aware(datetime(2026, 5, 23, 19, 30)),
            status="upcoming",
            api_match_id="live-ipl-match-4"
        )
        self.stdout.write(f"Created upcoming match: {m6}")

        # Match 7: Upcoming (MI vs RR, May 24, 2026 3:30 PM)
        m7 = Match.objects.create(
            team_a=teams["MI"],
            team_b=teams["RR"],
            match_datetime=timezone.make_aware(datetime(2026, 5, 24, 15, 30)),
            status="upcoming",
            api_match_id="live-ipl-match-5"
        )
        self.stdout.write(f"Created upcoming match: {m7}")

        # Match 8: Upcoming (KKR vs DC, May 24, 2026 7:30 PM)
        m8 = Match.objects.create(
            team_a=teams["KKR"],
            team_b=teams["DC"],
            match_datetime=timezone.make_aware(datetime(2026, 5, 24, 19, 30)),
            status="upcoming",
            api_match_id="live-ipl-match-6"
        )
        self.stdout.write(f"Created upcoming match: {m8}")

        # 7. Create Demo Predictions for Completed Matches
        # Deduced initial bet amounts immediately on creation to preserve double-spend protection
        self.stdout.write("Seeding demo predictions...")

        # Karan Match 1 Prediction (Win) - predicted SRH (winner)
        p_karan_1 = Prediction.objects.create(
            user=users["karan"],
            room=room,
            match=m1,
            market_type="winner",
            selected_value=str(teams["SRH"].id),
            bet_amount=200,
            multiplier=1.5,
            status="pending"
        )
        users["karan"].profile.coin_balance -= 200
        users["karan"].profile.save()

        # Karan Match 2 Prediction (Win) - predicted RR (winner)
        p_karan_2 = Prediction.objects.create(
            user=users["karan"],
            room=room,
            match=m2,
            market_type="winner",
            selected_value=str(teams["RR"].id),
            bet_amount=150,
            multiplier=1.5,
            status="pending"
        )
        users["karan"].profile.coin_balance -= 150
        users["karan"].profile.save()

        # Rahul Match 1 Prediction (Loss) - predicted CSK (winner)
        p_rahul_1 = Prediction.objects.create(
            user=users["rahul"],
            room=room,
            match=m1,
            market_type="winner",
            selected_value=str(teams["CSK"].id),
            bet_amount=300,
            multiplier=1.5,
            status="pending"
        )
        users["rahul"].profile.coin_balance -= 300
        users["rahul"].profile.save()

        # Priya Match 1 Prediction (Win) - predicted SRH (winner)
        p_priya_1 = Prediction.objects.create(
            user=users["priya"],
            room=room,
            match=m1,
            market_type="winner",
            selected_value=str(teams["SRH"].id),
            bet_amount=100,
            multiplier=1.5,
            status="pending"
        )
        users["priya"].profile.coin_balance -= 100
        users["priya"].profile.save()

        # Priya Match 2 Prediction (Loss) - predicted LSG (winner)
        p_priya_2 = Prediction.objects.create(
            user=users["priya"],
            room=room,
            match=m2,
            market_type="winner",
            selected_value=str(teams["LSG"].id),
            bet_amount=250,
            multiplier=1.5,
            status="pending"
        )
        users["priya"].profile.coin_balance -= 250
        users["priya"].profile.save()

        # 8. Settle the Historical Predictions using utils
        self.stdout.write("Settling historical predictions...")
        settle_match_predictions(m1)
        settle_match_predictions(m2)

        # Refresh profiles from database to get correct settled balances!
        for user in users.values():
            user.profile.refresh_from_db()

        self.stdout.write(f"Karan coin balance: {users['karan'].profile.coin_balance} (Expected 1175)")
        self.stdout.write(f"Priya coin balance: {users['priya'].profile.coin_balance} (Expected 800)")
        self.stdout.write(f"Rahul coin balance: {users['rahul'].profile.coin_balance} (Expected 700)")

        # Create active pending predictions on Match 3 (KKR vs MI)
        # Karan predicts Match Winner: KKR (bet 200)
        # Priya predicts Match Winner: KKR (bet 150)
        # Rahul predicts Match Winner: MI (bet 250)
        Prediction.objects.create(
            user=users["karan"],
            room=room,
            match=m3,
            market_type="winner",
            selected_value=str(teams["KKR"].id),
            bet_amount=200,
            multiplier=1.5,
            confidence_level="medium",
            status="pending"
        )
        users["karan"].profile.coin_balance -= 200
        users["karan"].profile.save()

        Prediction.objects.create(
            user=users["priya"],
            room=room,
            match=m3,
            market_type="winner",
            selected_value=str(teams["KKR"].id),
            bet_amount=150,
            multiplier=1.5,
            confidence_level="high",
            status="pending"
        )
        users["priya"].profile.coin_balance -= 150
        users["priya"].profile.save()

        Prediction.objects.create(
            user=users["rahul"],
            room=room,
            match=m3,
            market_type="winner",
            selected_value=str(teams["MI"].id),
            bet_amount=250,
            multiplier=1.5,
            confidence_level="medium",
            status="pending"
        )
        users["rahul"].profile.coin_balance -= 250
        users["rahul"].profile.save()

        # Recalculate weekly champions for the room just to seed champion history
        self.stdout.write("Calculating weekly champions...")
        calculate_weekly_champions(room, check_date=timezone.now().date())

        self.stdout.write("CricStake database seeding completed successfully!")
