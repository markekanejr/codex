from django.urls import path

from . import views

urlpatterns = [
    path("", views.today, name="today"),
    path("plans/", views.plans, name="plans"),
    path("plans/new/", views.plan_edit, name="plan_new"),
    path("plans/<int:pk>/edit/", views.plan_edit, name="plan_edit"),
    path("plans/export/", views.export_plans, name="export_plans"),
    path("routines/new/", views.routine_edit, name="routine_new"),
    path("routines/<int:pk>/edit/", views.routine_edit, name="routine_edit"),
    path("sources/new/", views.source_edit, name="source_new"),
    path("sources/<int:pk>/edit/", views.source_edit, name="source_edit"),
    path("trips/", views.trips, name="trips"),
    path("trips/new/", views.trip_edit, name="trip_new"),
    path("trips/<int:pk>/", views.trip_detail, name="trip_detail"),
    path("trips/<int:pk>/edit/", views.trip_edit, name="trip_edit"),
    path("trips/<int:trip_pk>/segments/new/", views.segment_edit, name="segment_new"),
    path("trips/<int:trip_pk>/segments/<int:pk>/edit/", views.segment_edit, name="segment_edit"),
    path("settings/", views.household_settings, name="household_settings"),
    path("invite/<str:token>/", views.invitation_accept, name="invitation_accept"),
    path("health/", views.health, name="health"),
    path("briefing/", views.briefing, name="briefing"),
    path("review/", views.review, name="review"),
    path("review/new/", views.action_edit, name="action_new"),
    path("review/<int:pk>/", views.action_detail, name="action_detail"),
    path("review/<int:pk>/edit/", views.action_edit, name="action_edit"),
    path("review/<int:pk>/decide/", views.action_decide, name="action_decide"),
    path("settings/budget/", views.budget_settings, name="budget_settings"),
]
