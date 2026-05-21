from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # General / Landing
    path('', views.landing_view, name='landing'),
    
    # Auth
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Password Reset
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),
    
    # Dashboard & Profile
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/<str:username>/', views.profile_view, name='user_profile'),
    
    # Rooms
    path('room/create/', views.room_create_view, name='room_create'),
    path('room/join/', views.room_join_view, name='room_join'),
    path('room/<int:room_id>/', views.room_detail_view, name='room_detail'),
    path('room/<int:room_id>/settings/', views.room_settings_view, name='room_settings'),
    path('room/<int:room_id>/leave/', views.room_leave_view, name='room_leave'),
    path('room/<int:room_id>/kick/<int:user_id>/', views.room_kick_member_view, name='room_kick'),
    path('room/<int:room_id>/history/', views.room_history_view, name='room_history'),
    
    # Predictions
    path('room/<int:room_id>/match/<int:match_id>/predict/', views.match_predict_view, name='match_predict'),
]
