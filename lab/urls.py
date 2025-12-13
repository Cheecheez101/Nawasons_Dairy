from django.urls import path
from . import views

app_name = "lab"

urlpatterns = [
    # Add a raw milk test for a specific yield
    path(
        "yield/<int:yield_id>/add_raw_test/",
        views.add_raw_test,
        name="add_raw_test"
    ),

    # Add a tank batch test for a specific yield
    path(
        "yield/<int:yield_id>/add_tank_test/",
        views.add_tank_test,
        name="add_tank_test"
    ),

    # Approve a specific production batch
    path(
        "batch/<int:batch_id>/approve/",
        views.approve_batch,
        name="approve_batch"
    ),

    # View all tests for a specific yield
    path(
        "yield/<int:yield_id>/tests/",
        views.milk_yield_tests,
        name="milk_yield_tests"
    ),
    path("dashboard/", views.lab_dashboard, name="dashboard"),
    # Approve/reject tank batch tests
    path("tank_test/<int:test_id>/<str:action>/", views.approve_tank_test, name="approve_tank_test"),
    # View all yields for a given tank
    path("tank/<str:tank>/yields/", views.milk_yield_tests, name="tank_yield_tests"),
    # Create a tank-level test (lab selects tank, sees quantity and chooses a yield)
    path("tank/<str:tank>/create_test/", views.create_tank_test, name="create_tank_test"),

]
