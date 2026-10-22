from celery import shared_task

from apps.organizations.models import Organization

from . import recommendations, services


@shared_task(name="analytics.collect_metrics")
def collect_metrics() -> int:
    return services.collect_due()


@shared_task(name="analytics.generate_recommendations")
def generate_all_recommendations() -> int:
    count = 0
    for org in Organization.objects.all().iterator():
        recommendations.generate(org)
        count += 1
    return count
