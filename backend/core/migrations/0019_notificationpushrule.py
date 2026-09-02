import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0018_shift_release_requested_worker'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationPushRule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('key', models.CharField(max_length=80, unique=True)),
                ('enabled', models.BooleanField(default=True)),
                ('title_template', models.CharField(blank=True, default='{title}', max_length=240)),
                ('body_template', models.TextField(blank=True, default='{body}')),
            ],
            options={'ordering': ['key']},
        ),
    ]
