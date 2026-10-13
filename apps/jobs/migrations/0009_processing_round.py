from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('jobs', '0008_job_history'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='processing_round',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.RemoveConstraint(
            model_name='job',
            name='unique_follow_up_per_source_event',
        ),
        migrations.AddConstraint(
            model_name='job',
            constraint=models.UniqueConstraint(
                fields=('source_job', 'processing_round', 'job_type', 'source_event'),
                name='unique_follow_up_source_round_event',
            ),
        ),
    ]
