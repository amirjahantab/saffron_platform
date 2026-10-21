from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST
from apps.catalog.models import Product
from .forms import TicketForm, ReplyForm, ReviewForm
from .models import Ticket, Reply, Review

LOGIN = "storefront:login_page"


@never_cache
@login_required(login_url=LOGIN)
@require_http_methods(["GET", "POST"])
def inbox(request):
    from apps.core.limits import enforce_limit
    form = TicketForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        if not enforce_limit(f"ticket:{request.user.pk}", 10, 3600):
            form.add_error(None, "تعداد درخواست‌ها بیش از حد مجاز است؛ کمی بعد تلاش کنید.")
        else:
            with transaction.atomic():
                item = form.save()
                Reply.objects.create(ticket=item, author=request.user, body=form.cleaned_data["body"])
            return redirect("care:ticket", public_id=item.public_id)
    return render(request, "care/inbox.html", {"form": form, "tickets": request.user.ticket_set.all()[:50], "page_title": "پشتیبانی جهانتاب"})


@never_cache
@login_required(login_url=LOGIN)
@require_http_methods(["GET", "POST"])
def ticket(request, public_id):
    from apps.core.limits import enforce_limit
    item = get_object_or_404(Ticket, public_id=public_id, user=request.user)
    form = ReplyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not enforce_limit(f"reply:{request.user.pk}", 30, 3600):
            form.add_error(None, "تعداد پیام‌ها بیش از حد مجاز است.")
        else:
            with transaction.atomic():
                Reply.objects.create(ticket=item, author=request.user, body=form.cleaned_data["body"])
                item.status = "open"
                item.save(update_fields=["status", "updated_at"])
            return redirect("care:ticket", public_id=item.public_id)
    return render(request, "care/ticket.html", {"ticket": item, "replies": item.replies.filter(is_internal=False).select_related("author"), "form": form, "page_title": item.subject})


@login_required(login_url=LOGIN)
@require_POST
def review(request, slug):
    from django.core.exceptions import ValidationError
    product = get_object_or_404(Product, slug=slug, is_active=True)
    entry = Review(product=product, user=request.user)
    form = ReviewForm(request.POST, instance=entry)
    if form.is_valid():
        try:
            with transaction.atomic():
                form.save()
            messages.success(request, "نظر شما ثبت شد و پس از بررسی منتشر می‌شود.")
        except (IntegrityError, ValidationError):
            messages.error(request, "نظر این محصول قبلاً ثبت شده است.")
    else:
        messages.error(request, "برای ثبت نظر، خرید پرداخت‌شده و امتیاز معتبر لازم است؛ هر حساب برای هر محصول یک نظر ثبت می‌کند.")
    return redirect("storefront:product_detail", slug=slug)
