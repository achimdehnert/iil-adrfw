"""meiki-hub Fallakten model — UUID tenant_id."""

from django.db import models


class CaseDocument(models.Model):
    """A scanned case file referenced in meiki-hub."""

    # tenant_id is UUID (matches all consumer-repo conventions)
    tenant_id = models.UUIDField(db_index=True)

    case_number = models.CharField(max_length=50, db_index=True)
    title = models.CharField(max_length=255)
    content_text = models.TextField()
    scanned_at = models.DateTimeField(auto_now_add=True)
