from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Case, Count, IntegerField, Value, When
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import BookingRequestForm, CompanionProfileForm, SignUpForm
from .models import ActivityTag, Availability, CompanionProfile


def home(request):
    profiles = CompanionProfile.objects.filter(status=CompanionProfile.Status.APPROVED, is_paused=False)
    city = request.GET.get("city", "").strip()
    activity = request.GET.get("activity", "").strip()
    gender = request.GET.get("gender", "").strip()
    language = request.GET.get("language", "").strip()
    minimum = request.GET.get("min_price", "").strip()
    maximum = request.GET.get("max_price", "").strip()
    available_day = request.GET.get("available_day", "").strip()
    rating = request.GET.get("rating", "").strip()
    plan = request.GET.get("plan", "").strip()
    sort = request.GET.get("sort", "relevance")

    if city:
        profiles = profiles.filter(city__icontains=city)
    if activity:
        profiles = profiles.filter(activities__slug=activity)
    if gender:
        profiles = profiles.filter(gender=gender)
    if language:
        profiles = profiles.filter(languages__icontains=language)
    if minimum.isdigit():
        profiles = profiles.filter(hourly_rate__gte=int(minimum))
    if maximum.isdigit():
        profiles = profiles.filter(hourly_rate__lte=int(maximum))
    if available_day.isdigit() and int(available_day) in range(7):
        profiles = profiles.filter(availability__weekday=int(available_day))
    if plan in CompanionProfile.Plan.values:
        profiles = profiles.filter(plan=plan)

    profiles = profiles.annotate(avg_rating=Avg("bookings__review__rating"), review_count=Count("bookings__review"))
    if rating.isdigit() and int(rating) in range(1, 6):
        profiles = profiles.filter(avg_rating__gte=int(rating))
    if sort == "price":
        profiles = profiles.order_by("hourly_rate", "-plan", "-created_at")
    elif sort == "newest":
        profiles = profiles.order_by("-created_at")
    else:
        profiles = profiles.annotate(plan_order=Case(
            When(plan=CompanionProfile.Plan.GOLD, then=Value(3)),
            When(plan=CompanionProfile.Plan.SILVER, then=Value(2)),
            default=Value(1),
            output_field=IntegerField(),
        )).order_by("-is_verified", "-plan_order", "-avg_rating", "-created_at")

    page_obj = Paginator(profiles.distinct(), 9).get_page(request.GET.get("page"))
    return render(request, "marketplace/home.html", {
        "profiles": page_obj.object_list,
        "page_obj": page_obj,
        "activities": ActivityTag.objects.filter(is_active=True),
        "filters": request.GET,
        "gender_choices": CompanionProfile.Gender.choices,
        "plan_choices": CompanionProfile.Plan.choices,
        "weekday_choices": Availability._meta.get_field("weekday").choices,
    })


def profile_detail(request, slug):
    profile = get_object_or_404(
        CompanionProfile.objects.prefetch_related("activities", "photos", "availability")
        .annotate(avg_rating=Avg("bookings__review__rating"), review_count=Count("bookings__review")),
        slug=slug,
        status=CompanionProfile.Status.APPROVED,
        is_paused=False,
    )
    reviews = profile.bookings.filter(status="completed", review__isnull=False).select_related("review", "client")
    return render(request, "marketplace/profile_detail.html", {"profile": profile, "reviews": reviews})


@login_required
@require_http_methods(["GET", "POST"])
def request_booking(request, slug):
    companion = get_object_or_404(
        CompanionProfile,
        slug=slug,
        status=CompanionProfile.Status.APPROVED,
        is_paused=False,
    )
    if companion.user_id == request.user.id:
        messages.error(request, "You cannot request a session with your own listing.")
        return redirect("profile_detail", slug=slug)

    form = BookingRequestForm(request.POST or None, companion=companion)
    if form.is_valid():
        booking = form.save(commit=False)
        booking.client = request.user
        booking.save()
        messages.success(request, "Request sent. The companion has 24 hours to respond.")
        return redirect("profile_detail", slug=slug)
    return render(request, "marketplace/booking_request.html", {"profile": companion, "form": form})


def sign_up(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = SignUpForm(request.POST or None)
    if form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("home")
    return render(request, "registration/signup.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def companion_apply(request):
    if CompanionProfile.objects.filter(user=request.user).exists():
        messages.info(request, "Your companion application is already on file.")
        return redirect("home")
    form = CompanionProfileForm(request.POST or None)
    if form.is_valid():
        profile = form.save(commit=False)
        profile.user = request.user
        profile.status = CompanionProfile.Status.PENDING
        profile.public_meeting_places_only = True
        profile.save()
        form.save_m2m()
        messages.success(request, "Application received. Your listing will go live after review and membership activation.")
        return redirect("home")
    return render(request, "marketplace/companion_apply.html", {"form": form})


@login_required
def my_plans(request):
    Booking.objects.filter(
        companion__user=request.user,
        status=Booking.Status.REQUESTED,
        created_at__lt=timezone.now() - timedelta(hours=24),
    ).update(status=Booking.Status.EXPIRED)
    incoming = Booking.objects.filter(companion__user=request.user).select_related(
        "client", "companion", "activity"
    )
    outgoing = Booking.objects.filter(client=request.user).select_related(
        "companion", "activity"
    )
    return render(request, "marketplace/my_plans.html", {
        "incoming": incoming,
        "outgoing": outgoing,
        "today": timezone.localdate(),
    })


@login_required
@require_http_methods(["POST"])
def update_booking(request, booking_id, action):
    booking = get_object_or_404(
        Booking.objects.select_related("companion"),
        pk=booking_id,
    )
    if booking.status == Booking.Status.REQUESTED and booking.created_at < timezone.now() - timedelta(hours=24):
        booking.status = Booking.Status.EXPIRED
        booking.save(update_fields=["status"])
        messages.info(request, "This request expired after 24 hours.")
        return redirect("my_plans")

    if action in ("accept", "decline"):
        if booking.companion.user_id != request.user.id or booking.status != Booking.Status.REQUESTED:
            return HttpResponseForbidden("This booking cannot be changed by this account.")
        booking.status = Booking.Status.ACCEPTED if action == "accept" else Booking.Status.DECLINED
    elif action == "cancel":
        if booking.client_id != request.user.id or booking.status not in (
            Booking.Status.REQUESTED,
            Booking.Status.ACCEPTED,
        ):
            return HttpResponseForbidden("This booking cannot be cancelled by this account.")
        booking.status = Booking.Status.CANCELLED
    else:
        return HttpResponseForbidden("Unsupported booking action.")

    booking.save(update_fields=["status"])
    messages.success(request, f"Booking {booking.get_status_display().lower()}.")
    return redirect("my_plans")