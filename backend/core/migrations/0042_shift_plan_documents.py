from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0041_provision_spenerhaus_client_portal'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ShiftPlanDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('file', models.FileField(upload_to='shift_plans/%Y/%m/')),
                ('original_name', models.CharField(max_length=255)),
                ('checksum', models.CharField(db_index=True, max_length=64, unique=True)),
                ('extracted_event_numbers', models.JSONField(blank=True, default=list)),
                ('extracted_event_dates', models.JSONField(blank=True, default=list)),
                ('extracted_service_windows', models.JSONField(blank=True, default=dict)),
                ('extracted_preview', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('client', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='shift_plan_documents', to='core.clientcompany')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_shift_plan_documents', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='ShiftPlanAttachment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('match_score', models.PositiveSmallIntegerField(default=0)),
                ('match_reason', models.CharField(blank=True, max_length=500)),
                ('matched_automatically', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('attached_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='attached_shift_plans', to=settings.AUTH_USER_MODEL)),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='core.shiftplandocument')),
                ('shift', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='plan_attachments', to='core.shift')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='shiftplanattachment',
            constraint=models.UniqueConstraint(fields=('shift', 'document'), name='unique_shift_plan_document'),
        ),
    ]
