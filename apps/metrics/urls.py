from django.urls import path

from .views import (
    MetricsFailureRateView,
    MetricsJobTypesView,
    MetricsSummaryView,
)

urlpatterns = [
    path('summary/', MetricsSummaryView.as_view(), name='metrics-summary'),
    path('job-types/', MetricsJobTypesView.as_view(), name='metrics-job-types'),
    path(
        'failure-rate/',
        MetricsFailureRateView.as_view(),
        name='metrics-failure-rate',
    ),
]
