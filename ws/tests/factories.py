from datetime import datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import allauth.account.models as account_models
import factory
import factory.fuzzy
from django.contrib.auth.models import User
from factory.django import DjangoModelFactory
from mitoc_const import affiliations

import ws.utils.dates as date_utils
from ws import enums, models


class BaseFactory(DjangoModelFactory):
    class Meta:
        skip_postgeneration_save = True


class EmergencyContactFactory(BaseFactory):
    class Meta:
        model = models.EmergencyContact

    name = "My Mother"
    cell_phone = "+17815550342"
    relationship = "Mother"
    email = "mum@example.com"


class EmergencyInfoFactory(BaseFactory):
    class Meta:
        model = models.EmergencyInfo

    emergency_contact = factory.SubFactory(EmergencyContactFactory)
    allergies = "None"
    medications = "None"
    medical_history = "None"


class EmailAddressFactory(BaseFactory):
    class Meta:
        model = account_models.EmailAddress

    email = factory.LazyAttribute(lambda obj: obj.user.email)
    verified = True
    primary = True


class UserFactory(BaseFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n + 1}")
    email = factory.Sequence(lambda n: f"user{n + 1}@example.com")
    emailaddress = factory.RelatedFactory(EmailAddressFactory, "user")
    password = "password"  # (Will be hashed & salted by `create_user`)  # noqa: S105

    @classmethod
    def _create(cls, model_class: type[User], *args: Any, **kwargs: Any) -> Any:
        """Behave like `create_user` -- coerce password to a hashed/salted equivalent.

        We pretty much have no reason to initialize a user with a hashed/salted password,
        instead preferring to work with plaintext passwords.
        """
        manager = cls._get_manager(model_class)
        return manager.create_user(*args, **kwargs)


class MembershipFactory(BaseFactory):
    class Meta:
        model = models.Membership

    membership_expires = factory.LazyAttribute(
        lambda _obj: date_utils.local_date() + timedelta(days=365)
    )
    waiver_expires = factory.LazyAttribute(
        lambda _obj: date_utils.local_date() + timedelta(days=365)
    )


class ParticipantFactory(BaseFactory):
    class Meta:
        model = models.Participant

    affiliation = affiliations.NON_AFFILIATE.CODE
    membership = factory.SubFactory(MembershipFactory)
    email = factory.Sequence(lambda n: f"participant{n + 1}@example.com")
    name = "Test Participant"
    car = None
    emergency_info = factory.SubFactory(EmergencyInfoFactory)

    @staticmethod
    def _given_user(kwargs: dict[str, Any]) -> User | None:
        if "user" in kwargs:
            return cast(User, kwargs["user"])
        if "user_id" in kwargs:
            return User.objects.get(pk=kwargs["user_id"])
        return None

    @classmethod
    def create(cls, **kwargs: Any) -> Any:  # Participant, but factory-boy declares Any
        """If a user is specified, sync these two objects.

        (User records live in a different database, so we must do this fetch
        to keep them in sync).
        """
        user = cls._given_user(kwargs)
        if user:
            kwargs.pop("user", None)  # (If given, not meaningful)
            kwargs["user_id"] = user.pk
            kwargs["_disable_auto_user_creation"] = True

            # By default, use the user's email address
            if "email" not in kwargs:
                kwargs["email"] = user.email
        return super().create(**kwargs)

    @classmethod
    def _create(cls, model_class: type[User], *args: Any, **kwargs: Any) -> Any:
        """Create a corresponding user whenever we make a Participant.

        Each Participant stores the ID of its user, but it's not truly a
        foreign key, since the row resides in another database. Accordingly,
        we cannot use a SubFactory for the User object.
        """
        if not kwargs.pop("_disable_auto_user_creation", False):
            user = UserFactory.create(email=kwargs["email"])
            kwargs["user_id"] = user.pk

        return super()._create(model_class, *args, **kwargs)


class MembershipReminderFactory(BaseFactory):
    class Meta:
        model = models.MembershipReminder

    participant = factory.SubFactory(ParticipantFactory)
    reminder_sent_at = factory.fuzzy.FuzzyDateTime(
        start_dt=datetime(2021, 11, 13, tzinfo=ZoneInfo("UTC"))
    )


class PasswordQualityFactory(BaseFactory):
    class Meta:
        model = models.PasswordQuality

    participant = factory.SubFactory(ParticipantFactory)


class CarFactory(BaseFactory):
    class Meta:
        model = models.Car

    license_plate = "ABC 123"
    state = "MA"
    make = "Powell Motors"
    model = "Homer"
    year = 2019
    color = "Green"


class LeaderRatingFactory(BaseFactory):
    class Meta:
        model = models.LeaderRating

    activity = models.LeaderRating.HIKING
    rating = "Full leader"
    creator = factory.SubFactory(ParticipantFactory)
    participant = factory.SubFactory(ParticipantFactory)
    active = True


class LeaderRecommendationFactory(BaseFactory):
    class Meta:
        model = models.LeaderRecommendation

    activity = models.LeaderRating.HIKING
    rating = "Should co-lead two trips"
    creator = factory.SubFactory(ParticipantFactory)
    participant = factory.SubFactory(ParticipantFactory)


class LotteryInfoFactory(BaseFactory):
    class Meta:
        model = models.LotteryInfo

    participant = factory.SubFactory(ParticipantFactory)
    car_status = "rent"
    paired_with = None


class LotterySeparationFactory(BaseFactory):
    class Meta:
        model = models.LotterySeparation

    creator = factory.SubFactory(ParticipantFactory)
    initiator = factory.SubFactory(ParticipantFactory)
    recipient = factory.SubFactory(ParticipantFactory)


class LotteryAdjustmentFactory(BaseFactory):
    class Meta:
        model = models.LotteryAdjustment

    creator = factory.SubFactory(ParticipantFactory)
    participant = factory.SubFactory(ParticipantFactory)
    expires = factory.LazyAttribute(lambda _obj: date_utils.next_lottery())


class TripFactory(BaseFactory):
    class Meta:
        model = models.Trip

    name = factory.Sequence(lambda n: f"Test Trip #{n + 1}")
    description = "An awesome trip into the Whites"
    difficulty_rating = "Intermediate"
    winter_terrain_level = "B"
    activity = "winter_school"  # TODO: Remove!
    trip_type = enums.TripType.HIKING.value
    program = enums.Program.WINTER_SCHOOL.value
    creator = factory.SubFactory(ParticipantFactory)


class TripInfoFactory(BaseFactory):
    class Meta:
        model = models.TripInfo


class FeedbackFactory(BaseFactory):
    class Meta:
        model = models.Feedback

    participant = factory.SubFactory(ParticipantFactory)
    leader = factory.SubFactory(ParticipantFactory)
    trip = factory.SubFactory(TripFactory)
    comments = "Participant did a great job."


class SignUpFactory(BaseFactory):
    class Meta:
        model = models.SignUp

    participant = factory.SubFactory(ParticipantFactory)
    trip = factory.SubFactory(TripFactory)
    notes = ""
    order = None
    manual_order = None
    on_trip = False


class WaitListSignupFactory(BaseFactory):
    class Meta:
        model = models.WaitListSignup

    signup = factory.SubFactory(SignUpFactory)
    waitlist = factory.SelfAttribute("signup.trip.waitlist")


class ClimbingLeaderApplicationFactory(BaseFactory):
    class Meta:
        model = models.ClimbingLeaderApplication

    participant = factory.SubFactory(ParticipantFactory)
    years_climbing = 9
    years_climbing_outside = 7
    outdoor_bouldering_grade = "V3"
    outdoor_sport_leading_grade = "5.11"
    outdoor_trad_leading_grade = "Trad is too rad for me"

    # These fields are all choices in a set enum!
    familiarity_spotting = "none"
    familiarity_bolt_anchors = "very comfortable"
    familiarity_gear_anchors = "none"
    familiarity_sr = "some"

    # Below fields are optional
    spotting_description = ""
    tr_anchor_description = ""
    rappel_description = ""
    gear_anchor_description = ""
    formal_training = "Wilderness First Responder"
    teaching_experience = "Leader in my college outing club"
    notable_climbs = "The Nose of El Capitan"
    favorite_route = "Jaws II"
    extra_info = "An extinct giant sloth is largely responsible for the existence of the avocado."


class HikingLeaderApplicationFactory(BaseFactory):
    class Meta:
        model = models.HikingLeaderApplication

    participant = factory.SubFactory(ParticipantFactory)
    desired_rating = "Leader"

    mitoc_experience = "Member for 3 years, been to 2 Circuses, never led a trip"
    formal_training = "Wilderness First Responder"
    leadership_experience = "Leader in my college outing club"


class WinterSchoolLeaderApplicationFactory(BaseFactory):
    class Meta:
        model = models.WinterSchoolLeaderApplication

    participant = factory.SubFactory(ParticipantFactory)
    desired_rating = "B coC"
    taking_wfa = "No"
    training = "EMT Basic"
    technical_skills = "I know how to self arrest"
    winter_experience = "Several years hiking in the Whites"
    ice_experience = ""  # (No experience)
    ski_experience = ""  # (No experience)
    other_experience = "Leader in my college outing club"


class LectureAttendanceFactory(BaseFactory):
    class Meta:
        model = models.LectureAttendance

    participant = factory.SubFactory(ParticipantFactory)
    creator = factory.SubFactory(ParticipantFactory)
