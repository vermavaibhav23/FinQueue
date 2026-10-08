from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Job
from .rate_limits import check_job_submission_rate_limit
from .serializers import JobSerializer, JobSubmitSerializer
from .services import enqueue_job, remove_job_from_queues


class JobSubmitView(generics.CreateAPIView):
    serializer_class = JobSubmitSerializer
    permission_classes = (IsAuthenticated,)

    def create(self, request, *args, **kwargs):
        check_job_submission_rate_limit(request.user)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = serializer.save()
        enqueue_job(job)

        return Response(
            {
                'id': job.id,
                'job_type': job.job_type,
                'priority': job.priority,
                'status': job.status,
                'created_at': job.created_at,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class JobListView(generics.ListAPIView):
    serializer_class = JobSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = Job.objects.filter(user=self.request.user)
        status_filter = self.request.query_params.get('status')
        job_type_filter = self.request.query_params.get('job_type')

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        if job_type_filter:
            queryset = queryset.filter(job_type=job_type_filter)

        return queryset


class JobDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = JobSerializer
    permission_classes = (IsAuthenticated,)
    lookup_field = 'id'
    lookup_url_kwarg = 'job_id'

    def get_queryset(self):
        return Job.objects.filter(user=self.request.user)

    def perform_destroy(self, instance):
        if instance.status != Job.Status.PENDING:
            raise ValidationError('Only pending jobs can be cancelled.')

        remove_job_from_queues(instance.id)
        instance.delete()
