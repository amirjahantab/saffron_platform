from pathlib import Path
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.http import require_GET
from apps.catalog.models import LabCertificate


@require_GET
def certificate(request, public_id):
    item = get_object_or_404(LabCertificate.objects.filter(is_verified=True, harvest_batch__is_active=True,
        harvest_batch__variants__is_active=True, harvest_batch__variants__product__is_active=True,
        harvest_batch__variants__packaging_type__is_active=True).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=timezone.localdate())).distinct(), public_id=public_id)
    try:
        document = item.document_file.open("rb")
    except (OSError, ValueError):
        raise Http404 from None
    response = FileResponse(document, as_attachment=True, filename=f"certificate-{item.public_id}{Path(item.document_file.name).suffix}")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def block_raw_documents(request, path=""):
    raise Http404
