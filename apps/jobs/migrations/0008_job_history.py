from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0007_unify_idempotency_into_job'),
    ]

    operations = [
        migrations.CreateModel(
            name='JobHistory',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('pending', 'Pending'),
                            ('running', 'Running'),
                            ('completed', 'Completed'),
                            ('failed', 'Failed'),
                            ('dead', 'Dead'),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    'retry_count',
                    models.PositiveSmallIntegerField(default=0),
                ),
                (
                    'message',
                    models.TextField(blank=True, null=True),
                ),
                (
                    'created_at',
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    'job',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='history',
                        to='jobs.job',
                    ),
                ),
            ],
            options={
                'db_table': 'job_history',
                'ordering': ('created_at',),
                'indexes': [
                    models.Index(
                        fields=['job', 'created_at'],
                        name='jobs_jobhis_job_id_03db4e_idx',
                    ),
                ],
            },
        ),
    ]
}
