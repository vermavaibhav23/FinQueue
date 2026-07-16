from django.urls import path

from .views import JobDetailView, JobListView, JobSubmitView

urlpatterns = [
    path('submit/', JobSubmitView.as_view(), name='job-submit'),
    path('', JobListView.as_view(), name='job-list'),
    path('<uuid:job_id>/', JobDetailView.as_view(), name='job-detail'),
]
