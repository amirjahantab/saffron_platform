import json
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from .services import answer


@never_cache
@require_GET
def page(request):
    return render(request, "assistant/page.html", {"page_title": "دستیار انتخاب زعفران"})


@never_cache
@require_POST
def ask(request):
    if len(request.body) > 6000:
        return JsonResponse({"message": "پیام بیش از حد طولانی است."}, status=400)
    try:
        data = json.loads(request.body)
        message = data.get("message")
        if not isinstance(message, str) or not 2 <= len(message.strip()) <= 1000:
            raise ValueError
    except (ValueError, AttributeError, UnicodeDecodeError):
        return JsonResponse({"message": "پیام باید بین ۲ تا ۱۰۰۰ نویسه باشد."}, status=400)
    return JsonResponse(answer(request, message.strip()))
