from django.contrib import admin
from .models import Article, ArticleRedirect, Category, FAQ, PolicyPage, StoreProfile, Tag


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "author", "status", "published_at")
    list_filter = ("status", "category", "tags")
    search_fields = ("title", "body")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("products", "tags")


@admin.register(PolicyPage)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_published", "updated_at")


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "is_published", "position")
    list_editable = ("is_published", "position")


admin.site.register([Category, Tag])


@admin.register(StoreProfile)
class StoreProfileAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not StoreProfile.objects.exists() and super().has_add_permission(request)


@admin.register(ArticleRedirect)
class RedirectAdmin(admin.ModelAdmin):
    list_display = ("old_slug", "article")
    readonly_fields = ("old_slug", "article")

    def has_add_permission(self, request):
        return False
