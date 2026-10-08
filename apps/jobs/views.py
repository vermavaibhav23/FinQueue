import hashlib
import json

from django.db import IntegrityError, transaction
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import IdempotencyRequest, Job
from .rate_limits import check_job_submission_rate_limit
from .serializers import JobSerializer, JobSubmitSerializer
from .services import enqueue_job, remove_job_from_queues


class JobSubmitView(generics.CreateAPIView):
    serializer_class = JobSubmitSerializer
    permission_classes = (IsAuthenticated,)

    def create(self, request, *args, **kwargs):
        idempotency_key = request.headers.get('Idempotency-Key', '').strip()

        if not idempotency_key:
            raise ValidationError(
                {'idempotency_key': 'Idempotency-Key header is required.'}
            )

        if len(idempotency_key) > 128:
            raise ValidationError(
                {'idempotency_key': 'Idempotency-Key must be at most 128 characters.'}
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        request_hash = self._request_hash(serializer.validated_data)

        existing = (
            IdempotencyRequest.objects.select_related('job')
            .filter(
                user=request.user,
                idempotency_key=idempotency_key,
            )
            .first()
        )

        if existing is not None:
            return self._replay_or_conflict(existing, request_hash)

        check_job_submission_rate_limit(request.user)

        try:
            with transaction.atomic():
                job = serializer.save()
                IdempotencyRequest.objects.create(
                    user=request.user,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    job=job,
                )
                transaction.on_commit(lambda: enqueue_job(job))
        except IntegrityError:
            # Another request with the same merchant + key may have won the race.
            existing = IdempotencyRequest.objects.select_related('job').get(
                user=request.user,
                idempotency_key=idempotency_key,
            )
            return self._replay_or_conflict(existing, request_hash)

        return self._job_response(
            job,
            status_code=status.HTTP_202_ACCEPTED,
            idempotent_replay=False,
        )

    @staticmethod
    def _request_hash(validated_data):
        canonical_body = {
            'job_type': validated_data['job_type'],
            'payload': validated_data['payload'],
        }
        canonical_json = json.dumps(
            canonical_body,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

    def _replay_or_conflict(self, existing, request_hash):
        if existing.request_hash != request_hash:
            return Response(
                {
                    'detail': (
                        'This Idempotency-Key was already used with a different request.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        return self._job_response(
            existing.job,
            status_code=status.HTTP_200_OK,
            idempotent_replay=True,
        )

    @staticmethod
    def _job_response(job, status_code, idempotent_replay):
        return Response(
            {
                'id': job.id,
                'job_type': job.job_type,
                'priority': job.priority,
                'status': job.status,
                'created_at': job.created_at,
                'idempotent_replay': idempotent_replay,
            },
            status=status_code,
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
