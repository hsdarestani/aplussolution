from django.db import migrations


QA_CLIENT_EMAIL = "qa.client.contracts@aplus-solution.de"
QA_CLIENT_PASSWORD_HASH = "pbkdf2_sha256$1000000$qozZp4qbVjer$cucG3VgaiIM/Xtf6qzSbCW1AXD6HPbzaefTuTecPfew="


def reset_qa_client_password(apps, schema_editor):
    User = apps.get_model("core", "User")
    User.objects.filter(email=QA_CLIENT_EMAIL).update(
        password=QA_CLIENT_PASSWORD_HASH,
        is_active=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0019_notificationpushrule"),
    ]

    operations = [
        migrations.RunPython(reset_qa_client_password, migrations.RunPython.noop),
    ]
