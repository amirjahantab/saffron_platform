from urllib.parse import urlsplit
from xml.etree.ElementTree import Element, SubElement, tostring

from django.conf import settings
from django.contrib.sitemaps.views import sitemap
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from .sitemaps import ProductsSitemap, StorePagesSitemap, ArticlesSitemap, PoliciesSitemap

SITEMAPS = {"pages": StorePagesSitemap, "products": ProductsSitemap, "articles": ArticlesSitemap, "policies": PoliciesSitemap}


def _maps():
    scheme = urlsplit(settings.SITE_URL).scheme
    maps = {key: cls() for key, cls in SITEMAPS.items()}
    for item in maps.values():
        item.protocol = scheme
        item.get_domain = lambda site=None: urlsplit(settings.SITE_URL).netloc
    return maps


@require_GET
def sitemap_index(request):
    root = Element("sitemapindex", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for section, section_map in _maps().items():
        for page in section_map.paginator.page_range:
            location = settings.SITE_URL + reverse("sitemap-section", args=[section])
            if page > 1:
                location += f"?p={page}"
            SubElement(SubElement(root, "sitemap"), "loc").text = location
    return HttpResponse(tostring(root, encoding="utf-8", xml_declaration=True), content_type="application/xml")


@require_GET
def sitemap_section(request, section):
    if section not in SITEMAPS:
        raise Http404
    return sitemap(request, sitemaps=_maps(), section=section)


@require_GET
def robots(request):
    # Leave private URLs crawlable so crawlers can observe their noindex headers.
    content = "User-agent: *\nAllow: /\nSitemap: " + settings.SITE_URL + "/sitemap.xml\n"
    return HttpResponse(content, content_type="text/plain; charset=utf-8")
