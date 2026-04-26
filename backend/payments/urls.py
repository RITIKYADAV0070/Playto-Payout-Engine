from django.urls import path

from . import views

urlpatterns = [
    path("merchants", views.merchants),
    path("dashboard", views.dashboard),
    path("payouts", views.payouts),
]
