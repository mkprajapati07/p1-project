from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from .models import Booking, CompanionProfile, Report


@staff_member_required(login_url="login")
def dashboard(request):
    today = timezone.localdate()
    pending_profiles = CompanionProfile.objects.filter(
        status=CompanionProfile.Status.PENDING
    ).select_related("user").order_by("created_at")
    review_queue = pending_profiles[:6]
    attention_bookings = Booking.objects.filter(
        status__in=(Booking.Status.REQUESTED, Booking.Status.ACCEPTED)
    ).select_related("client", "companion", "activity").order_by("date", "start_time")[:8]
    open_reports = Report.objects.filter(
        status=Report.Status.OPEN
    ).select_related("reporter", "target_user").order_by("created_at")[:6]

    plan_labels = dict(CompanionProfile.Plan.choices)
    plan_mix = [
        {"label": plan_labels[item["plan"]], "total": item["total"]}
        for item in CompanionProfile.objects.values("plan").annotate(
            total=Count("pk")
        ).order_by("plan")
    ]
    context = {
        "user_count": get_user_model().objects.count(),
        "live_listing_count": CompanionProfile.objects.filter(
            status=CompanionProfile.Status.APPROVED,
            is_paused=False,
        ).count(),
        "pending_profile_count": pending_profiles.count(),
        "upcoming_booking_count": Booking.objects.filter(
            status=Booking.Status.ACCEPTED,
            date__gte=today,
        ).count(),
        "open_report_count": Report.objects.filter(status=Report.Status.OPEN).count(),
        "review_queue": review_queue,
        "attention_bookings": attention_bookings,
        "open_reports": open_reports,
        "plan_mix": plan_mix,
    }
    return render(request, "admin_panel/dashboard.html", context)