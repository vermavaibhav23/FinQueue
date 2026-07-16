from django.urls import path

from .views import DeadLetterQueueListView, DeadLetterQueueRequeueView

urlpatterns = [
    path('', DeadLetterQueueListView.as_view(), name='dlq-list'),
    path(
        '<int:dlq_id>/requeue/',
        DeadLetterQueueRequeueView.as_view(),
        name='dlq-requeue',
    ),
]
