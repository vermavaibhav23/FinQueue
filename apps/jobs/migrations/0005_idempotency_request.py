import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('jobs', '0004_job_source_follow_ups'),
    ]

    operations = [
        migrations.CreateModel(
            name='IdempotencyRequest',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ('idempotency_key', models.CharField(max_length=128)),
                ('request_hash', models.CharField(max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'job',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='idempotency_request',
                        to='jobs.job',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='idempotency_requests',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'db_table': 'idempotency_requests',
            },
        ),
        migrations.AddConstraint(
            model_name='idempotencyrequest',
            constraint=models.UniqueConstraint(
                fields=('user', 'idempotency_key'),
                name='unique_user_idempotency_key',
            ),
        ),
    ]
