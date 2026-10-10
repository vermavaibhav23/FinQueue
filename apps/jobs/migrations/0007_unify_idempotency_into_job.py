from django.db import migrations, models


def copy_idempotency_to_jobs(apps, schema_editor):
    Job = apps.get_model('jobs', 'Job')
    IdempotencyRequest = apps.get_model('jobs', 'IdempotencyRequest')

    for entry in IdempotencyRequest.objects.all().iterator():
        Job.objects.filter(pk=entry.job_id).update(
            idempotency_key=entry.idempotency_key,
            request_hash=entry.request_hash,
        )


def restore_idempotency_requests(apps, schema_editor):
    Job = apps.get_model('jobs', 'Job')
    IdempotencyRequest = apps.get_model('jobs', 'IdempotencyRequest')

    entries = []
    for job in Job.objects.exclude(idempotency_key__isnull=True).iterator():
        entries.append(
            IdempotencyRequest(
                user_id=job.user_id,
                idempotency_key=job.idempotency_key,
                request_hash=job.request_hash,
                job_id=job.id,
            )
        )

    if entries:
        IdempotencyRequest.objects.bulk_create(entries)


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0006_remove_transaction'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='idempotency_key',
            field=models.CharField(
                blank=True,
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='job',
            name='request_hash',
            field=models.CharField(
                blank=True,
                max_length=64,
                null=True,
            ),
        ),
        migrations.RunPython(
            copy_idempotency_to_jobs,
            restore_idempotency_requests,
        ),
        migrations.AddConstraint(
            model_name='job',
            constraint=models.UniqueConstraint(
                fields=('user', 'idempotency_key'),
                name='unique_job_user_idempotency_key',
            ),
        ),
        migrations.DeleteModel(
            name='IdempotencyRequest',
        ),
    ]
}
