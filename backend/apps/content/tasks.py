from celery import shared_task
from django.conf import settings

from . import video

_LIMIT = settings.VIDEO_RENDER_TIMEOUT_SECONDS + 120


@shared_task(name="content.render_video", acks_late=True, time_limit=_LIMIT)
def render_video(job_id: str) -> None:
    video.execute(job_id)
