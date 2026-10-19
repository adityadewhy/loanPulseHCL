import os
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from loanpulse_app.models import User


class Command(BaseCommand):
    help = "Create or update the first LoanPulse administrator from environment variables."

    def handle(self, *args, **options):
        email = os.getenv("BOSS_EMAIL", "").strip().lower()
        password = os.getenv("BOSS_PASSWORD", "")
        full_name = os.getenv("BOSS_NAME", "LoanPulse Boss").strip()
        if not email or not 12 <= len(password) <= 128:
            raise CommandError("Set BOSS_EMAIL and a BOSS_PASSWORD between 12 and 128 characters in .env.")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        user, created = User.objects.get_or_create(email=email, defaults={
            "full_name": full_name, "role": "ADMIN", "hashed_password": make_password(password), "is_active": True,
        })
        if not created:
            if user.role != "ADMIN":
                raise CommandError("BOSS_EMAIL is already used by a non-admin account.")
            user.full_name = full_name
            user.hashed_password = make_password(password)
            user.is_active = True
            user.save(update_fields=["full_name", "hashed_password", "is_active"])
        self.stdout.write(self.style.SUCCESS(f"Boss administrator {'created' if created else 'updated'}: {email}"))
