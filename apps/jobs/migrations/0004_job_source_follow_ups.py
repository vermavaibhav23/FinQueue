from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0003_update_job_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='source_job',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='follow_up_jobs',
                to='jobs.job',
            ),
        ),
        migrations.AddField(
            model_name='job',
            name='source_event',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddConstraint(
            model_name='job',
            constraint=models.UniqueConstraint(
                fields=('source_job', 'job_type', 'source_event'),
                name='unique_follow_up_per_source_event',
            ),
        ),
    ]
