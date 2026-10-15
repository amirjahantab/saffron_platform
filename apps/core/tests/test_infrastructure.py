"""Tests for healthcheck endpoint, management command, and security headers."""
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse


class InfrastructureHealthTests(TestCase):
    """Test suite for /health/ endpoint and verify_infrastructure command."""

    def test_health_check_endpoint_returns_200_when_healthy(self) -> None:
        url = reverse("core:health_check")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["services"]["database"], "ok")
        self.assertEqual(data["services"]["cache"], "ok")
        # Ensure health check responses are never cached by proxies
        self.assertIn("no-cache", response.headers.get("Cache-Control", ""))

    @patch("apps.core.views.check_cache_health", return_value=(False, "unreachable"))
    def test_health_check_endpoint_returns_503_when_cache_fails(self, _mock_cache: object) -> None:
        url = reverse("core:health_check")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data["status"], "unhealthy")
        self.assertEqual(data["services"]["cache"], "unreachable")

    @patch("apps.core.views.check_database_health", return_value=(False, "unreachable"))
    def test_health_check_endpoint_returns_503_when_db_fails(self, _mock_db: object) -> None:
        url = reverse("core:health_check")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data["status"], "unhealthy")
        self.assertEqual(data["services"]["database"], "unreachable")

    def test_health_check_rejects_post_requests(self) -> None:
        url = reverse("core:health_check")
        response = self.client.post(url)
        self.assertEqual(response.status_code, 405)

    def test_verify_infrastructure_command_succeeds(self) -> None:
        out = StringIO()
        call_command("verify_infrastructure", stdout=out)
        output_text = out.getvalue()
        self.assertIn("[OK] Database connection verified", output_text)
        self.assertIn("[OK] Cache connection verified", output_text)
        self.assertIn("[OK] Currency contract verified", output_text)

    @patch("apps.core.management.commands.verify_infrastructure.check_cache_health", return_value=(False, "down"))
    def test_verify_infrastructure_command_raises_on_failure(self, _mock_cache: object) -> None:
        with self.assertRaises(CommandError):
            call_command("verify_infrastructure", stdout=StringIO())
            