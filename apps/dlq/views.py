from rest_framework import generics, status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DeadLetterQueue
from .serializers import DeadLetterQueueSerializer
from .services import requeue_dead_letter_job


class DeadLetterQueueListView(generics.ListAPIView):
    queryset = DeadLetterQueue.objects.select_related('original_job').all()
    serializer_class = DeadLetterQueueSerializer
    permission_classes = (IsAdminUser,)


class DeadLetterQueueRequeueView(APIView):
    permission_classes = (IsAdminUser,)

    def post(self, request, dlq_id):
        dlq_entry = get_object_or_404(
            DeadLetterQueue.objects.select_related('original_job'),
            id=dlq_id,
        )
        job, queue_score = requeue_dead_letter_job(dlq_entry)

        return Response(
            {
                'detail': 'Job requeued successfully.',
                'job_id': job.id,
                'status': job.status,
                'queue_score': queue_score,
            },
            status=status.HTTP_200_OK,
        )
