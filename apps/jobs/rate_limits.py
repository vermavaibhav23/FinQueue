from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import Throttled


def check_job_submission_rate_limit(user):
    cache_key = f'job-submit-rate:{user.id}'
    limit = settings.JOB_SUBMISSION_RATE_LIMIT
    window_seconds = settings.JOB_SUBMISSION_RATE_WINDOW_SECONDS

    added = cache.add(cache_key, 1, timeout=window_seconds)

    if added:
        return

    current_count = cache.incr(cache_key)

    if current_count > limit:
        ttl = cache.ttl(cache_key)
        raise Throttled(
            detail='Too many job submissions. Please try again later.',
            wait=max(ttl, 1),
        )
