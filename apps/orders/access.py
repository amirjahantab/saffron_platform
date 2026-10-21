import hashlib
import secrets


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def owns_order(request, order):
    if order.user_id is not None:
        return request.user.is_authenticated and order.user_id == request.user.pk
    token = request.session.get("guest_orders", {}).get(order.order_number, "")
    return bool(token and order.guest_access_hash and secrets.compare_digest(token_digest(token), order.guest_access_hash))
