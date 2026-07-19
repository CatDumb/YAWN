from django.contrib import admin
from django.urls import include, path

from config.views import health, ready

urlpatterns = [
    path("health/", health, name="health"),
    path("ready/", ready, name="ready"),
    path("admin/", admin.site.urls),
    path("api/", include("config.api_urls")),
]
