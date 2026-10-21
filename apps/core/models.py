
"""Abstract base models used across all domain applications."""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """
    Abstract base class model that provides self-updating
    `created_at` and `updated_at` timestamp fields.
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_("تاریخ ایجاد"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("تاریخ آخرین ویرایش"),
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class UUIDModel(models.Model):
    """ 
    Abstract base class that provides a non-enumerable UUID field (`public_id`)
    for safe external exposure in URLs and APIs while keeping integer PKs for internal joins.
    """

    public_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        verbose_name=_("شناسه عمومی"),
    )

    class Meta:
        abstract = True


class DemoDataset(models.Model):
    """Persistent marker preventing an accidentally seeded database going live."""
    name = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
