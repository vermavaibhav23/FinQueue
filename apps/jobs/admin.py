from django.contrib import admin

from .models import Job, JobHistory


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


@admin.register(JobHistory)
class JobHistoryAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'job',
        'status',
        'retry_count',
        'message',
        'created_at',
    )
    list_filter = ('status',)
    search_fields = ('job__id', 'job__user__username', 'message')
    readonly_fields = (
        'job',
        'status',
        'retry_count',
        'message',
        'created_at',
    )
