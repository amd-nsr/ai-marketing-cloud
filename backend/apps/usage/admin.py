from django.contrib import admin

from .models import OrganizationQuota


@admin.register(OrganizationQuota)
class OrganizationQuotaAdmin(admin.ModelAdmin[OrganizationQuota]):
    list_display = [
        "organization",
        "ai_requests_per_month",
        "ai_cost_per_month_usd",
        "storage_bytes",
    ]
    search_fields = ["organization__name"]
