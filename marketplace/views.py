from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Avg, Case, Count, IntegerField, Q, Value, When
from django.db import transaction
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import AvailabilityFormSet, BookingRequestForm, CompanionProfileForm, ReportForm, SignUpForm
from .models import AccountProfile, ActivityTag, Availability, Block, Booking, CompanionProfile


def home(request):
    profiles = CompanionProfile.objects.filter(status=CompanionProfile.Status.APPROVED, is_paused=False)
    if request.user.is_authenticated:
        blocked_users = Block.objects.filter(
            Q(blocker=request.user) | Q(target=request.user)
        ).values_list("blocker_id", "target_id")
        hidden_user_ids = {user_id for pair in blocked_users for user_id in pair if user_id != request.user.id}
        profiles = profiles.exclude(user_id__in=hidden_user_ids)
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
    if request.user.is_authenticated and Block.objects.filter(
        Q(blocker=request.user, target=profile.user) | Q(blocker=profile.user, target=request.user)
    ).exists():
        return redirect("home")
    reviews = profile.bookings.filter(status="completed", review__isnull=False).select_related("review", "client")
    return render(request, "marketplace/profile_detail.html", {"profile": profile, "reviews": reviews})


@login_required
@require_http_methods(["GET", "POST"])
def request_booking(request, slug):
    account, _ = AccountProfile.objects.get_or_create(user=request.user)
    if account.role != AccountProfile.Role.CLIENT:
        messages.error(request, "Companion accounts cannot request client bookings.")
        return redirect("home")
    companion = get_object_or_404(
        CompanionProfile,
        slug=slug,
        status=CompanionProfile.Status.APPROVED,
        is_paused=False,
    )
    if companion.user_id == request.user.id:
        messages.error(request, "You cannot request a session with your own listing.")
        return redirect("profile_detail", slug=slug)
    if Block.objects.filter(
        Q(blocker=request.user, target=companion.user) | Q(blocker=companion.user, target=request.user)
    ).exists():
        messages.error(request, "This booking is unavailable because one account has blocked the other.")
        return redirect("home")

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
        AccountProfile.objects.create(user=user, role=form.cleaned_data["role"])
        login(request, user)
        if form.cleaned_data["role"] == AccountProfile.Role.COMPANION:
            return redirect("companion_apply")
        return redirect("home")
    return render(request, "registration/signup.html", {"form": form})


@login_required
def dashboard(request):
    account, _ = AccountProfile.objects.get_or_create(user=request.user)
    destination = "companion_dashboard" if account.role == AccountProfile.Role.COMPANION else "client_dashboard"
    return redirect(destination)


@login_required
def client_dashboard(request):
    account, _ = AccountProfile.objects.get_or_create(user=request.user)
    if account.role == AccountProfile.Role.COMPANION:
        return redirect("companion_dashboard")

    bookings = Booking.objects.filter(client=request.user)
    upcoming = bookings.filter(
        status=Booking.Status.ACCEPTED,
        date__gte=timezone.localdate(),
    ).select_related("companion", "activity").order_by("date", "start_time")[:5]
    context = {
        "pending_count": bookings.filter(status=Booking.Status.REQUESTED).count(),
        "upcoming_count": bookings.filter(status=Booking.Status.ACCEPTED, date__gte=timezone.localdate()).count(),
        "completed_count": bookings.filter(status=Booking.Status.COMPLETED).count(),
        "upcoming": upcoming,
    }
    return render(request, "marketplace/client_dashboard.html", context)


@login_required
def companion_dashboard(request):
    account, _ = AccountProfile.objects.get_or_create(user=request.user)
    if account.role != AccountProfile.Role.COMPANION:
        return redirect("client_dashboard")

    profile = CompanionProfile.objects.filter(user=request.user).first()
    if profile:
        bookings = profile.bookings.all()
        requests = bookings.filter(status=Booking.Status.REQUESTED).select_related(
            "client", "activity"
        ).order_by("created_at")[:5]
        upcoming_count = bookings.filter(
            status=Booking.Status.ACCEPTED,
            date__gte=timezone.localdate(),
        ).count()
        completed_count = bookings.filter(status=Booking.Status.COMPLETED).count()
        request_count = bookings.filter(status=Booking.Status.REQUESTED).count()
    else:
        requests = Booking.objects.none()
        upcoming_count = 0
        completed_count = 0
        request_count = 0

    return render(request, "marketplace/companion_dashboard.html", {
        "profile": profile,
        "requests": requests,
        "upcoming_count": upcoming_count,
        "completed_count": completed_count,
        "request_count": request_count,
    })


@login_required
@require_http_methods(["GET", "POST"])
def manage_availability(request):
    account, _ = AccountProfile.objects.get_or_create(user=request.user)
    if account.role != AccountProfile.Role.COMPANION:
        return redirect("client_dashboard")
    profile = get_object_or_404(CompanionProfile, user=request.user)
    formset = AvailabilityFormSet(request.POST or None, instance=profile, prefix="availability")
    if request.method == "POST" and formset.is_valid():
        formset.save()
        messages.success(request, "Your weekly availability has been updated.")
        return redirect("companion_dashboard")
    return render(request, "marketplace/availability.html", {"profile": profile, "formset": formset})


@login_required
@require_http_methods(["GET", "POST"])
def companion_apply(request):
    account, _ = AccountProfile.objects.get_or_create(user=request.user)
    if account.role != AccountProfile.Role.COMPANION:
        messages.error(request, "Choose the Companion role when creating your account to submit a listing.")
        return redirect("home")
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
@require_http_methods(["POST"])
def report_profile(request, slug):
    profile = get_object_or_404(CompanionProfile, slug=slug)
    if profile.user_id == request.user.id:
        messages.error(request, "You cannot report your own profile.")
        return redirect("profile_detail", slug=slug)
    form = ReportForm(request.POST)
    if form.is_valid():
        report = form.save(commit=False)
        report.reporter = request.user
        report.target_user = profile.user
        report.save()
        messages.success(request, "Your report was sent to our safety team.")
    else:
        messages.error(request, "Please provide a reason for the report.")
    return redirect("profile_detail", slug=slug)


@login_required
@require_http_methods(["POST"])
def block_profile(request, slug):
    profile = get_object_or_404(CompanionProfile, slug=slug)
    if profile.user_id == request.user.id:
        messages.error(request, "You cannot block your own account.")
    else:
        Block.objects.get_or_create(blocker=request.user, target=profile.user)
        messages.success(request, "This account is now blocked and will be hidden from your discovery.")
    return redirect("home")


@login_required
def blocked_users(request):
    blocks = Block.objects.filter(blocker=request.user).select_related("target").order_by("-created_at")
    return render(request, "marketplace/blocked_users.html", {"blocks": blocks})


@login_required
@require_http_methods(["POST"])
def unblock_user(request, block_id):
    Block.objects.filter(pk=block_id, blocker=request.user).delete()
    messages.success(request, "The account was unblocked.")
    return redirect("blocked_users")


@login_required
def my_plans(request):
    account, _ = AccountProfile.objects.get_or_create(user=request.user)
    if account.role == AccountProfile.Role.COMPANION:
        Booking.objects.filter(
            companion__user=request.user,
            status=Booking.Status.REQUESTED,
            created_at__lt=timezone.now() - timedelta(hours=24),
        ).update(status=Booking.Status.EXPIRED)
        incoming = Booking.objects.filter(companion__user=request.user).select_related(
            "client", "companion", "activity"
        )
        outgoing = Booking.objects.none()
    else:
        incoming = Booking.objects.none()
        outgoing = Booking.objects.filter(client=request.user).select_related(
            "companion", "activity"
        )
    return render(request, "marketplace/my_plans.html", {
        "incoming": incoming,
        "outgoing": outgoing,
        "is_companion": account.role == AccountProfile.Role.COMPANION,
        "today": timezone.localdate(),
    })


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def update_booking(request, booking_id, action):
    booking = get_object_or_404(
        Booking.objects.select_for_update().select_related("companion"),
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
        if action == "accept":
            booking.status = Booking.Status.ACCEPTED
            try:
                booking.full_clean()
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
                return redirect("my_plans")
        else:
            booking.status = Booking.Status.DECLINED
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