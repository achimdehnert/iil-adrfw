"""bfagent stories model — UUID tenant_id."""
from django.db import models


class Story(models.Model):
    tenant_id = models.UUIDField(db_index=True)
    title = models.CharField(max_length=200)


class Scene(models.Model):
    tenant_id = models.UUIDField(db_index=True)
    story = models.ForeignKey(Story, on_delete=models.CASCADE)
    body = models.TextField()
