from datetime import timedelta
from tempfile import TemporaryDirectory
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from apps.core.tests.factories import catalog
from apps.catalog.models import LabCertificate


class CertificateDownloadTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.media = override_settings(MEDIA_ROOT=self.temp.name)
        self.media.enable()
        self.addCleanup(self.media.disable)
        self.product, self.variant = catalog()
        self.cert = LabCertificate.objects.create(harvest_batch=self.variant.harvest_batch, lab_name="Lab", certificate_number="DL-1", issue_date=timezone.localdate()-timedelta(days=10), is_verified=True, document_file=SimpleUploadedFile("cert.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf"))

    def test_verified_document_download_uses_attachment_and_raw_media_is_blocked(self):
        response = self.client.get(self.cert.get_download_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-"))
        self.assertEqual(self.client.get(self.cert.document_file.url).status_code, 404)

    def test_unverified_expired_and_inactive_documents_are_not_public(self):
        self.cert.is_verified = False
        self.cert.save()
        self.assertEqual(self.client.get(self.cert.get_download_url()).status_code, 404)
        self.cert.is_verified = True
        self.cert.expiry_date = timezone.localdate()-timedelta(days=1)
        self.cert.save()
        self.assertEqual(self.client.get(self.cert.get_download_url()).status_code, 404)
        self.assertNotContains(self.client.get(f"/shop/{self.product.slug}/"), "DL-1")
        self.cert.expiry_date = None
        self.cert.save()
        self.product.is_active = False
        self.product.save()
        self.assertEqual(self.client.get(self.cert.get_download_url()).status_code, 404)
