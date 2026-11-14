from datetime import datetime, time, timedelta

from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.text import slugify
from django.utils import timezone


class ActivityTag(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AccountProfile(models.Model):
    class Role(models.TextChoices):
        CLIENT = "client", "Client"
        COMPANION = "companion", "Companion"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="marketplace_account")
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.CLIENT, db_index=True)
    phone = models.CharField(max_length=24, blank=True)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} ({self.get_role_display()})"


class CompanionProfile(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        SUSPENDED = "suspended", "Suspended"

    class Plan(models.TextChoices):
        BASIC = "basic", "Basic"
        SILVER = "silver", "Silver"
        GOLD = "gold", "Gold"

    class Gender(models.TextChoices):
        WOMAN = "woman", "Woman"
        MAN = "man", "Man"
        NON_BINARY = "non_binary", "Non-binary"
        PREFER_NOT_TO_SAY = "private", "Prefer not to say"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    display_name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=20, choices=Gender.choices)
    city = models.CharField(max_length=80, db_index=True)
    bio = models.TextField(max_length=1200)
    hourly_rate = models.PositiveIntegerField()
    min_hours = models.PositiveSmallIntegerField(default=2)
    languages = models.CharField(max_length=200, help_text="Separate languages with commas")
    activities = models.ManyToManyField(ActivityTag, related_name="profiles")
    plan = models.CharField(max_length=10, choices=Plan.choices, default=Plan.BASIC)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    is_verified = models.BooleanField(default=False)
    public_meeting_places_only = models.BooleanField(default=False)
    is_paused = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.display_name

    @property
    def age(self):
        today = timezone.localdate()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    @property
    def plan_priority(self):
        return {self.Plan.BASIC: 1, self.Plan.SILVER: 2, self.Plan.GOLD: 3}[self.plan]

    def clean(self):
        if self.date_of_birth and self.age < 18:
            raise ValidationError({"date_of_birth": "Companions must be at least 18 years old."})
        if self.hourly_rate < 1:
            raise ValidationError({"hourly_rate": "Hourly rate must be greater than zero."})

    def save(self, *args, **kwargs):
        if not self.slug and self.user_id:
            self.slug = f"{slugify(self.display_name)[:75]}-{self.user_id}"
        super().save(*args, **kwargs)


class ProfilePhoto(models.Model):
    profile = models.ForeignKey(CompanionProfile, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="companion-photos/%Y/%m/")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"Photo for {self.profile}"


class Availability(models.Model):
    profile = models.ForeignKey(CompanionProfile, on_delete=models.CASCADE, related_name="availability")
    weekday = models.PositiveSmallIntegerField(choices=[(i, label) for i, label in enumerate(
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    )])
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["weekday", "start_time"]

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError("Availability end time must be after start time.")


class Booking(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"
        EXPIRED = "expired", "Expired"

    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings")
    companion = models.ForeignKey(CompanionProfile, on_delete=models.CASCADE, related_name="bookings")
    activity = models.ForeignKey(ActivityTag, on_delete=models.PROTECT)
    date = models.DateField()
    start_time = models.TimeField()
    hours = models.PositiveSmallIntegerField()
    location = models.CharField(max_length=160, help_text="Name a public venue in the companion's city")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        errors = {}
        if self.date and self.date < timezone.localdate():
            errors["date"] = "Choose today or a future date."
        if self.date and self.date == timezone.localdate() and self.start_time:
            if self.start_time <= timezone.localtime().time():
                errors["start_time"] = "Choose a start time that is still in the future."
        if self.companion_id and self.hours and self.hours < self.companion.min_hours:
            errors["hours"] = f"This companion requires at least {self.companion.min_hours} hours."
        if self.hours is not None and self.hours < 1:
            errors["hours"] = "Booking duration must be at least one hour."
        if self.activity_id and self.companion_id and not self.companion.activities.filter(pk=self.activity_id).exists():
            errors["activity"] = "Choose an activity offered by this companion."
        if self.client_id and self.companion_id and Block.objects.filter(
            Q(blocker_id=self.client_id, target_id=self.companion.user_id)
            | Q(blocker_id=self.companion.user_id, target_id=self.client_id)
        ).exists():
            errors["companion"] = "This booking cannot be requested because one account has blocked the other."
        if self.companion_id and self.date and self.start_time and self.hours and self.hours > 0:
            start_minutes = self.start_time.hour * 60 + self.start_time.minute
            end_minutes = start_minutes + self.hours * 60
            if end_minutes > 24 * 60:
                errors["hours"] = "A booking must end before midnight."
            else:
                end_time = time(end_minutes // 60 % 24, end_minutes % 60)
                availability = self.companion.availability.filter(weekday=self.date.weekday())
                if not availability.exists():
                    errors["start_time"] = "This companion has not set availability for that day."
                elif not availability.filter(start_time__lte=self.start_time, end_time__gte=end_time).exists():
                    errors["start_time"] = "This time falls outside the companion's available hours."

                booking_start = datetime.combine(self.date, self.start_time)
                booking_end = booking_start + timedelta(hours=self.hours)
                accepted = Booking.objects.filter(
                    companion=self.companion,
                    date=self.date,
                    status=self.Status.ACCEPTED,
                ).exclude(pk=self.pk)
                for existing in accepted:
                    existing_start = datetime.combine(existing.date, existing.start_time)
                    existing_end = existing_start + timedelta(hours=existing.hours)
                    if booking_start < existing_end and booking_end > existing_start:
                        errors["start_time"] = "This companion already has an accepted booking during that time."
                        break
        if errors:
            raise ValidationError(errors)


class Review(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="review")
    rating = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=800, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.rating not in range(1, 6):
            raise ValidationError({"rating": "Rating must be between 1 and 5."})
        if self.booking_id and self.booking.status != Booking.Status.COMPLETED:
            raise ValidationError("Reviews are available after a completed session.")


class Report(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        REVIEWING = "reviewing", "Reviewing"
        RESOLVED = "resolved", "Resolved"

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports")
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports_received")
    reason = models.TextField(max_length=800)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.reporter_id and self.target_user_id and self.reporter_id == self.target_user_id:
            raise ValidationError("You cannot report your own account.")


class Block(models.Model):
    blocker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocks_created")
    target = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocks_received")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("blocker", "target"), name="unique_user_block"),
            models.CheckConstraint(condition=~models.Q(blocker=models.F("target")), name="block_other_user_only"),
        ]

    def clean(self):
        if self.blocker_id and self.target_id and self.blocker_id == self.target_id:
            raise ValidationError("You cannot block your own account.")