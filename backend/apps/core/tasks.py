from celery import shared_task


@shared_task(name="core.ping")
def ping() -> str:
    """Trivial task used to verify that the worker consumes from the broker."""
    return "pong"
