"""Synthetic billing app — three models, mix of compliant and drifted.

Used by tests/test_e2e.py to verify adr_check finds the right violations.
"""
from django.db import models


class CompliantInvoice(models.Model):
    """Should pass: tenant_id is BigIntegerField."""
    tenant_id = models.BigIntegerField(db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)


class DriftedSubscription(models.Model):
    """Should fail: tenant_id is plain IntegerField — classic int4 overflow risk."""
    tenant_id = models.IntegerField(db_index=True)  # noqa: VIOLATES ADR-099/tenant-id-bigint
    plan = models.CharField(max_length=50)
    status = models.CharField(max_length=20)


class AnotherDrifted(models.Model):
    """Should fail: tenant_id is PositiveIntegerField — same overflow class."""
    tenant_id = models.PositiveIntegerField()  # noqa: VIOLATES ADR-099/tenant-id-bigint
    name = models.CharField(max_length=100)


# Note: the "noqa" comments are illustrative — real exemptions go through
# the structured Exemption mechanism in the .rules.yaml file, not magic comments.
