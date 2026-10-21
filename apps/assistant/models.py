from django.db import models


class Usage(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(max_length=20)
    reserved_tokens = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    provider_response_id = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "مصرف دستیار"
        verbose_name_plural = "مصرف دستیار"
