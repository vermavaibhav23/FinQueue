from django.db.models import Count
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.jobs.models import Job


class MetricsSummaryView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        queryset = Job.objects.filter(user=request.user)
        status_counts = dict(
            queryset.values_list('status').annotate(total=Count('id'))
        )

        return Response(
            {
                'total_jobs': queryset.count(),
                'pending': status_counts.get(Job.Status.PENDING, 0),
                'running': status_counts.get(Job.Status.RUNNING, 0),
                'completed': status_counts.get(Job.Status.COMPLETED, 0),
                'failed': status_counts.get(Job.Status.FAILED, 0),
                'dead': status_counts.get(Job.Status.DEAD, 0),
            }
        )


class MetricsJobTypesView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        job_type_counts = (
            Job.objects.filter(user=request.user)
            .values('job_type')
            .annotate(total=Count('id'))
            .order_by('job_type')
        )

        return Response({'job_types': list(job_type_counts)})


class MetricsFailureRateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        queryset = Job.objects.filter(user=request.user)
        total_jobs = queryset.count()
        failed_jobs = queryset.filter(
            status__in=(Job.Status.FAILED, Job.Status.DEAD)
        ).count()
        failure_rate = 0

        if total_jobs:
            failure_rate = round((failed_jobs / total_jobs) * 100, 2)

        return Response(
            {
                'total_jobs': total_jobs,
                'failed_jobs': failed_jobs,
                'failure_rate_percent': failure_rate,
            }
        )
