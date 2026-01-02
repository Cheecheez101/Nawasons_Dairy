from django.urls import path

from . import views

app_name = "lab"

urlpatterns = [
    path("batch/<int:batch_id>/approve/", views.approve_batch, name="approve_batch"),
    path("batches/<int:batch_id>/edit/", views.batch_edit, name="batch_edit"),
    path("batches/", views.batch_list, name="batch_list"),
    path("batches/export/", views.batch_list_export, name="batch_list_export"),
    path("batches/<int:batch_id>/test/", views.batch_test_run, name="batch_test_run"),
    path("batch-tests/<int:test_id>/", views.batch_test_detail, name="batch_test_detail"),
    path("dashboard/", views.lab_dashboard, name="dashboard"),
    path("collection-sessions/admin/", views.collection_session_admin, name="session_admin"),
    path("collection-sessions/manage/", views.collection_session_toggle, name="collection_session_toggle"),
    path("approvals/", views.batch_approvals_index, name="batch_approvals"),
    path("batch-tests/", views.batch_tests_board, name="batch_tests"),
]
