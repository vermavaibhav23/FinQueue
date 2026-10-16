from django.db import migrations, models
import django.db.models.deletion


def keep_only_active_dead_entries(apps, schema_editor):
    """Clean up historic rows before enforcing one active DLQ entry per job."""
    DLQ = apps.get_model('dlq', 'DeadLetterQueue')
    alias = schema_editor.connection.alias
    entries = (
        DLQ.objects.using(alias)
        .order_by('-died_at', '-pk')
        .values_list('pk', 'original_job_id', 'original_job__status')
    )
    seen_jobs = set()
    to_delete = []
    for entry_id, job_id, status in entries.iterator():
        if status != 'dead' or job_id in seen_jobs:
            to_delete.append(entry_id)
        else:
            seen_jobs.add(job_id)
    for i in range(0, len(to_delete), 500):
        DLQ.objects.using(alias).filter(pk__in=to_delete[i:i + 500]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('dlq', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(keep_only_active_dead_entries, migrations.RunPython.noop),
        migrations.RemoveIndex(
            model_name='deadletterqueue',
            name='dead_letter_origina_9856a9_idx',
        ),
        migrations.AlterField(
            model_name='deadletterqueue',
            name='original_job',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='dead_letter_entry',
                to='jobs.job',
            ),
        ),
    ]
