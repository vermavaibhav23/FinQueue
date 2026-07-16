from django.core.management.base import BaseCommand

from apps.worker.recovery import recover_pending_jobs


class Command(BaseCommand):
    help = 'Re-push all pending jobs from MySQL into the Redis queue.'

    def handle(self, *args, **options):
        recovered_count = recover_pending_jobs()
        self.stdout.write(
            self.style.SUCCESS(f'Recovered {recovered_count} pending jobs.')
        )
