from django.db import migrations


REVIEW_EMAIL = "store-review@aplus-solution.de"
# PBKDF2-SHA256 hash for the dedicated Store review password. The plaintext
# password is intentionally not stored in the repository.
REVIEW_PASSWORD_HASH = "pbkdf2_sha256$1000000$uknDBax_fCIHUJqYLqLtyA$26a+GsJZD5rnNRxW85Tj7CBkjwrGhUZayS/VwCz2QZA="


def create_reviewer(apps, schema_editor):
    User = apps.get_model("core", "User")
    WorkerProfile = apps.get_model("core", "WorkerProfile")

    user, created = User.objects.get_or_create(
        email=REVIEW_EMAIL,
        defaults={
            "username": REVIEW_EMAIL,
            "first_name": "Store",
            "last_name": "Reviewer",
            "role": "worker",
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
            "password": REVIEW_PASSWORD_HASH,
        },
    )

    if not created:
        # Keep this account isolated as a normal worker and make the migration
        # idempotent for environments where the email was pre-created.
        user.username = REVIEW_EMAIL
        user.first_name = "Store"
        user.last_name = "Reviewer"
        user.role = "worker"
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.password = REVIEW_PASSWORD_HASH
        user.save(
            update_fields=[
                "username",
                "first_name",
                "last_name",
                "role",
                "is_active",
                "is_staff",
                "is_superuser",
                "password",
            ]
        )

    WorkerProfile.objects.get_or_create(
        user_id=user.pk,
        defaults={
            "employee_number": "STORE-REVIEW-001",
            "employment_type": "minijob",
            "monthly_hours": 0,
            "tariff_hourly_rate": 0,
            "extra_allowance": 0,
            "ranking_points": 0,
            "skills": [],
            "active": True,
        },
    )


def remove_reviewer(apps, schema_editor):
    User = apps.get_model("core", "User")
    User.objects.filter(email=REVIEW_EMAIL).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_alter_notification_kind"),
    ]

    operations = [
        migrations.RunPython(create_reviewer, remove_reviewer),
    ]
