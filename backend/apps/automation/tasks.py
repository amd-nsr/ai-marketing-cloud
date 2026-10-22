from celery import shared_task

from . import services


@shared_task(name="automation.run")
def run_automation() -> int:
    """Calendar auto-publishing and plan drafting for orgs with automation enabled."""
    count = 0
    for org in services.organizations_with_automation():
        count += services.run_calendar_autopublish(org)
        count += services.run_plan_drafting(org)
    return count


@shared_task(name="automation.reevaluate")
def reevaluate_deferred() -> int:
    """Deferred actions (paused, limits) are reconsidered regularly."""
    from .models import AutomationAction

    orgs = (
        AutomationAction.objects.filter(status=AutomationAction.Status.DEFERRED)
        .values_list("organization", flat=True)
        .distinct()
    )
    from apps.organizations.models import Organization

    for org in Organization.objects.filter(pk__in=list(orgs)):
        services.reevaluate_pending(org)
    return len(orgs)
