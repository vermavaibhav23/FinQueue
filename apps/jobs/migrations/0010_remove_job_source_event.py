from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('jobs', '0009_processing_round'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='job',
            constraint=models.UniqueConstraint(
                fields=('source_job', 'processing_round', 'job_type'),
                name='unique_follow_up_round_type',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='job',
            name='unique_follow_up_source_round_event',
        ),
        migrations.RemoveField(
            model_name='job',
            name='source_event',
        ),
    ]
