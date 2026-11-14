from django.contrib import admin

from .models import ActivityTag, Availability, Booking, CompanionProfile, ProfilePhoto, Report, Review


class ProfilePhotoInline(admin.TabularInline):
    model = ProfilePhoto
    extra = 0


@admin.register(CompanionProfile)
class CompanionProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "city", "plan", "status", "is_verified", "created_at")
    list_filter = ("status", "plan", "is_verified", "city")
    search_fields = ("display_name", "city", "user__email")
    list_editable = ("status",)
    filter_horizontal = ("activities",)
    inlines = (ProfilePhotoInline,)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "client", "companion", "date", "status", "created_at")
    list_filter = ("status", "date")
    search_fields = ("client__username", "companion__display_name")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("reporter", "target_user", "status", "created_at")
    list_filter = ("status", "created_at")
    list_editable = ("status",)


admin.site.register(ActivityTag)
admin.site.register(Availability)
admin.site.register(Review)