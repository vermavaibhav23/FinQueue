from django.contrib import admin

from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'job_type',
        'priority',
        'status',
        'idempotency_key',
        'retry_count',
        'created_at',
    )
    list_filter = ('job_type', 'priority', 'status')
    search_fields = ('id', 'user__username', 'idempotency_key')
    readonly_fields = ('id', 'created_at', 'updated_at')
