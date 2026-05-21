from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)

class ClosedSocialSignupAdapter(DefaultSocialAccountAdapter):
    """
    Custom social account adapter that blocks new social account registrations,
    but allows existing users with matching emails to log in and auto-links them.
    """
    def is_open_for_signup(self, request, sociallogin):
        # Programmatically prevent any new account from being created via Social OAuth
        return False

    def pre_social_login(self, request, sociallogin):
        # If the social account is already linked to a user, allauth handles it normally
        if sociallogin.is_existing:
            return
        
        # Check if a user with the social account's email already exists in the database
        email = sociallogin.user.email
        if email:
            try:
                user = User.objects.get(email=email)
                # Auto-link the social account to the existing user
                sociallogin.connect(request, user)
                logger.info(f"Auto-linked social account for email {email} to existing user {user.username}")
            except User.DoesNotExist:
                logger.warning(f"Social login signup attempt blocked for non-existent email: {email}")
                pass
