from django.db import models

from apps.jobs.models import Job


class DeadLetterQueue(models.Model):
    original_job = models.OneToOneField(
        Job,
        on_delete=models.CASCADE,
        related_name='dead_letter_entry',
    )
    job_type = models.CharField(max_length=32)
    payload = models.JSONField()
    failure_reason = models.TextField()
    retry_attempts = models.PositiveSmallIntegerField()
    died_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'dead_letter_queue'
        ordering = ('-died_at',)
        indexes = [
            models.Index(fields=('job_type', 'died_at')),
        ]

    def __str__(self):
        return f'{self.job_type} dead after {self.retry_attempts} retries'
