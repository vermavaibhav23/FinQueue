from django.contrib import admin

from .models import DeadLetterQueue


@admin.register(DeadLetterQueue)
class DeadLetterQueueAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'original_job',
        'job_type',
        'retry_attempts',
        'died_at',
    )
    list_filter = ('job_type', 'died_at')
    search_fields = ('original_job__id', 'failure_reason')
    readonly_fields = (
        'id',
        'original_job',
        'job_type',
        'payload',
        'failure_reason',
        'retry_attempts',
        'died_at',
    )
