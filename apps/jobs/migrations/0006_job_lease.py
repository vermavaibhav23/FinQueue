from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0005_idempotency_request'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='lease_expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='job',
            index=models.Index(
                fields=['status', 'lease_expires_at'],
                name='jobs_status_lease_idx',
            ),
        ),
    ]
