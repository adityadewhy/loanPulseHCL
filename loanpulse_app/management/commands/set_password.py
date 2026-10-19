import getpass

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from loanpulse_app.models import User


class Command(BaseCommand):
    help = "Set an account password using a hidden interactive prompt."

    def handle(self, *args, **options):
        email = input("Account email: ").strip().lower()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError("No account exists with that email.")
        password = getpass.getpass("New password (minimum 12 characters): ")
        confirmation = getpass.getpass("Confirm new password: ")
        if not 12 <= len(password) <= 128:
            raise CommandError("Password must be between 12 and 128 characters.")
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        if password != confirmation:
            raise CommandError("Passwords do not match.")
        user.hashed_password = make_password(password)
        user.save(update_fields=["hashed_password"])
        self.stdout.write(self.style.SUCCESS(f"Password updated for {user.email}."))
