from unittest.mock import patch
from django.core.cache import cache
from django.test import TestCase, override_settings, Client
from apps.core.tests.factories import user, catalog, paid_order
from .models import Usage
from .provider import AssistantProviderError


@override_settings(ASSISTANT_ENABLED=True, OPENAI_MODEL="explicit-test-model", OPENAI_API_KEY="test-only-key", ASSISTANT_DAILY_TOKEN_BUDGET=1000000)
class AssistantSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = user()
        self.product, self.variant = catalog()

    def ask(self, message="برای هدیه کدام محصول؟"):
        return self.client.post("/assistant/ask/", {"message": message}, content_type="application/json")

    @patch("apps.assistant.provider.OpenAIResponsesProvider.select")
    def test_model_selects_only_and_prices_are_read_from_database(self, provider):
        provider.return_value = ({"intent": "recommend", "product_slugs": [self.product.slug], "policy_slug": None}, {"input_tokens": 200, "output_tokens": 40}, "resp_test")
        data = self.ask().json()
        self.assertEqual(data["products"][0]["price"], self.variant.formatted_effective_price_toman)
        self.assertEqual(Usage.objects.get().output_tokens, 40)
        self.variant.base_price_rial = 600000
        self.variant.save()
        self.assertEqual(self.ask().json()["products"][0]["price"], self.variant.formatted_effective_price_toman)

    @patch("apps.assistant.provider.OpenAIResponsesProvider.select")
    def test_hallucinated_products_extra_fields_and_invalid_json_are_rejected(self, provider):
        for data in [{"intent": "recommend", "product_slugs": ["invented"], "policy_slug": None}, {"intent": "recommend", "product_slugs": [self.product.slug], "policy_slug": None, "price": 1}, ["unsafe"]]:
            provider.return_value = (data, {}, "x")
            response = self.ask().json()
            self.assertEqual(response["products"], [])
            self.assertIn("support_url", response)

    @patch("apps.assistant.provider.OpenAIResponsesProvider.select")
    def test_provider_failure_falls_back_without_leaking(self, provider):
        provider.side_effect = AssistantProviderError("secret should not appear")
        response = self.ask()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "secret should not appear")
        self.assertEqual(Usage.objects.get().status, "failed")

    @override_settings(ASSISTANT_ENABLED=False)
    @patch("apps.assistant.provider.OpenAIResponsesProvider.select")
    def test_disabled_never_calls_provider(self, provider):
        self.assertIn("غیرفعال", self.ask().json()["message"])
        provider.assert_not_called()

    @override_settings(ASSISTANT_DAILY_TOKEN_BUDGET=1)
    @patch("apps.assistant.provider.OpenAIResponsesProvider.select")
    def test_global_budget_prevents_request(self, provider):
        self.ask()
        provider.assert_not_called()

    @override_settings(ASSISTANT_HOURLY_LIMIT=1)
    @patch("apps.assistant.provider.OpenAIResponsesProvider.select")
    def test_hourly_budget_limits_requests(self, provider):
        provider.return_value = ({"intent": "unclear", "product_slugs": [], "policy_slug": None}, {}, "x")
        self.ask()
        self.ask()
        self.assertEqual(provider.call_count, 1)

    @patch("apps.assistant.provider.OpenAIResponsesProvider.select")
    def test_private_order_never_sent_to_model_or_other_user(self, provider):
        order = paid_order(self.owner, self.variant)
        self.assertNotIn("order_url", self.ask(order.order_number).json())
        other = user("09121110002")
        self.client.force_login(other)
        self.assertNotIn("order_url", self.ask(order.order_number).json())
        self.client.force_login(self.owner)
        self.assertIn("order_url", self.ask(order.order_number).json())
        provider.assert_not_called()

    def test_request_validation_and_csrf(self):
        self.assertEqual(self.ask("x").status_code, 400)
        self.assertEqual(self.ask("x" * 1001).status_code, 400)
        self.assertEqual(Client(enforce_csrf_checks=True).post("/assistant/ask/", {"message": "hi"}, content_type="application/json").status_code, 403)
