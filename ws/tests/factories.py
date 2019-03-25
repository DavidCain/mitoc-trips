from factory import SubFactory, Sequence
from factory.django import DjangoModelFactory

from mitoc_const import affiliations

from ws import models


class DiscountFactory(DjangoModelFactory):
    class Meta:
        model = models.Discount

    name = "Local Climbing Gym"
    active = True


class EmergencyContactFactory(DjangoModelFactory):
    class Meta:
        model = models.EmergencyContact

    name = "My Mother"
    cell_phone = "781-555-0342"
    relationship = "Mother"
    email = "mum@example.com"


class EmergencyInfoFactory(DjangoModelFactory):
    class Meta:
        model = models.EmergencyInfo

    emergency_contact = SubFactory(EmergencyContactFactory)
    allergies = "None"
    medications = "None"
    medical_history = "None"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = models.User

    username = Sequence(lambda n: f"user{n + 1}")
    email = Sequence(lambda n: f"user{n + 1}@example.com")


class ParticipantFactory(DjangoModelFactory):
    class Meta:
        model = models.Participant

    affiliation = affiliations.NON_AFFILIATE.CODE
    user_id = Sequence(lambda n: n + 1)
    email = Sequence(lambda n: f"participant{n + 1}@example.com")
    name = "Test Participant"
    emergency_info = SubFactory(EmergencyInfoFactory)

    @classmethod
    def create(cls, **kwargs):
        if 'user_id' in kwargs:
            kwargs['_disable_auto_user_creation'] = True
        return super().create(**kwargs)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """ Create a corresponding user whenever we make a Participant.

        Each Participant stores the ID of its user, but it's not truly a
        foreign key, since the row resides in another database. Accordingly,
        we cannot use a SubFactory for the User object.
        """
        if not kwargs.pop('_disable_auto_user_creation', False):
            UserFactory.create(id=kwargs['user_id'], email=kwargs['email'])

        return super()._create(model_class, *args, **kwargs)


class LotteryInfoFactory(DjangoModelFactory):
    class Meta:
        model = models.LotteryInfo
    participant = SubFactory(ParticipantFactory)


class TripFactory(DjangoModelFactory):
    class Meta:
        model = models.Trip

    name = Sequence(lambda n: f"Test Trip #{n + 1}")
    description = "An awesome trip into the Whites"
    difficulty_rating = "Intermediate"
    level = "B"
    activity = "winter_school"
    creator = SubFactory(ParticipantFactory)


class TripInfoFactory(DjangoModelFactory):
    class Meta:
        model = models.TripInfo


class FeedbackFactory(DjangoModelFactory):
    class Meta:
        model = models.Feedback

    participant = SubFactory(ParticipantFactory)
    leader = SubFactory(ParticipantFactory)
    trip = SubFactory(TripFactory)
    comments = "Participant did a great job."


class SignUpFactory(DjangoModelFactory):
    class Meta:
        model = models.SignUp

    participant = SubFactory(ParticipantFactory)
    trip = SubFactory(TripFactory)
    notes = ""
    order = None
    manual_order = None
    on_trip = False


class ClimbingLeaderApplicationFactory(DjangoModelFactory):
    class Meta:
        model = models.ClimbingLeaderApplication

    participant = SubFactory(ParticipantFactory)
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
