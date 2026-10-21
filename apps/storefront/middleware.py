from .seo import indexing_policy


class SearchIndexingMiddleware:
    """Keep private HTML, JSON, errors and redirects out of search engines."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code != 200 or not indexing_policy(request):
            response.headers["X-Robots-Tag"] = "noindex, follow"
        return response
