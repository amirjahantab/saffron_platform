from apps.orders.forms import CheckoutForm


class GuestCheckoutForm(CheckoutForm):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        self.fields.pop("shipping_address_public_id", None)
        self.fields.pop("save_address", None)
        labels = {"recipient_full_name": "نام و نام خانوادگی گیرنده", "recipient_phone": "شماره موبایل گیرنده", "province": "استان", "city": "شهر", "address_line": "نشانی کامل", "postal_code": "کد پستی ۱۰ رقمی", "shipping_method": "روش ارسال", "customer_note": "توضیحات سفارش"}
        for name, label in labels.items():
            self.fields[name].label = label
        from django.forms import HiddenInput
        self.fields["idempotency_key"].widget = HiddenInput()
