from django import template
from apps.catalog.image_assets import derivative_name

register = template.Library()


@register.inclusion_tag("components/_product_image.html")
def product_image(image, hero=False):
    srcset = []
    if image and image.image:
        storage = image.image.storage
        for size in (400, 800, 1200):
            name = derivative_name(image, size)
            if storage.exists(name):
                srcset.append(f"{storage.url(name)} {size}w")
    return {"image": image, "hero": hero, "optimized_srcset": ", ".join(srcset)}
