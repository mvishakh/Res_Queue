import ssl

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("smart_queue", broker=settings.redis_url, include=["app.workers.whatsapp_tasks"])

celery_app.conf.update(
    task_ignore_result=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    # Don't let the API hang if Redis is briefly unreachable; the outbox sweep covers it.
    task_publish_retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 0.5, "interval_max": 1},
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "whatsapp-outbox-sweep": {
            "task": "app.workers.whatsapp_tasks.dispatch_due_messages",
            "schedule": 30.0,
        }
    },
)

# Upstash and other TLS Redis providers use rediss:// URLs
if settings.redis_url.startswith("rediss://"):
    celery_app.conf.broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
