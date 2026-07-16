from django.contrib import admin

from .models import Job, Transaction


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'job_type',
        'priority',
        'status',
        'retry_count',
        'created_at',
    )
    list_filter = ('job_type', 'priority', 'status')
    search_fields = ('id', 'user__username')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'job',
        'user',
        'amount',
        'merchant',
        'status',
        'risk_score',
        'processed_at',
    )
    list_filter = ('status', 'currency')
    search_fields = ('id', 'job__id', 'user__username', 'merchant')
    readonly_fields = ('id', 'processed_at')
