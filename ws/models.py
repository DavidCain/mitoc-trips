from __future__ import unicode_literals

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse_lazy
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import string_concat

from localflavor.us.models import PhoneNumberField
from localflavor.us.models import USStateField
from ws.fields import OptionalOneToOneField
import ws.utils.dates as dateutils


pytz_timezone = timezone.get_default_timezone()


alphanum = RegexValidator(r'^[a-zA-Z0-9 ]*$',
                          "Only alphanumeric characters and spaces allowed")


class Car(models.Model):
    # As long as this module is reloaded once a year, this is fine
    # (First license plates were issued in Mass in 1903)
    year_min, year_max = 1903, dateutils.local_now().year + 2
    # Loosely validate - may wish to use international plates in the future
    license_plate = models.CharField(max_length=31, validators=[alphanum])
    state = USStateField()
    make = models.CharField(max_length=63)
    model = models.CharField(max_length=63)
    year = models.PositiveIntegerField(validators=[MaxValueValidator(year_max),
                                                   MinValueValidator(year_min)])
    color = models.CharField(max_length=63)

    def __unicode__(self):
        car_info = "{} {} {} {}".format(self.color, self.year, self.make, self.model)
        registration_info = "-".join([self.license_plate, self.state])
        return "{} ({})".format(car_info, registration_info)


class EmergencyContact(models.Model):
    name = models.CharField(max_length=255)
    cell_phone = PhoneNumberField()
    relationship = models.CharField(max_length=63)
    email = models.EmailField()

    def __unicode__(self):
        return "{} ({}): {}".format(self.name, self.relationship, self.cell_phone)


class EmergencyInfo(models.Model):
    emergency_contact = models.OneToOneField(EmergencyContact)
    allergies = models.CharField(max_length=255)
    medications = models.CharField(max_length=255)
    medical_history = models.TextField(max_length=2000,
                                       help_text="Anything your trip leader would want to know about.")

    def __unicode__(self):
        return ("Allergies: {} | Medications: {} | History: {} | "
                "Contact: {}".format(self.allergies, self.medications,
                                     self.medical_history, self.emergency_contact))


class LeaderManager(models.Manager):
    def get_queryset(self):
        all_participants = super(LeaderManager, self).get_queryset()
        leaders = all_participants.exclude(leaderrating=None)
        return leaders.prefetch_related('leaderrating_set')


class Participant(models.Model):
    """ Anyone going on a trip needs WIMP info, and info about their car.

    Even leaders will have a Participant record (see docstring of LeaderRating).
    """
    user_id = models.IntegerField()  # Technically a FK, but to another DB

    objects = models.Manager()
    leaders = LeaderManager()
    name = models.CharField(max_length=255)
    cell_phone = PhoneNumberField(null=True, blank=True)  # Hi, Sheep.
    last_updated = models.DateTimeField(auto_now=True)
    emergency_info = models.OneToOneField(EmergencyInfo)
    email = models.EmailField(unique=True, help_text=string_concat("This will be shared with leaders & other participants. <a href='",
                                                                   reverse_lazy('account_email'),
                                                                   "'>Change your account email</a>."))
    car = OptionalOneToOneField(Car)
    affiliation = models.CharField(max_length=1,
                                   choices=[('S', "MIT student"),
                                            ('M', "MIT affiliate"),
                                            ('N', "Non-affiliate")])
    attended_lectures = models.BooleanField(default=False)

    @property
    def user(self):
        return User.objects.prefetch_related('groups').get(pk=self.user_id)

    def name_with_rating(self, activity):
        rating = self.activity_rating(activity)
        return "{} ({})".format(self.name, rating) if rating else self.name

    def activity_rating(self, activity):
        """ Return leader's rating for the given activity (if one exists)."""
        # (We do this in raw Python instead of `filter()` to avoid n+1 queries
        # This method should be called when leaderrating_set was prefetched
        for rating in self.leaderrating_set.all():
            if rating.activity == activity:
                return rating.rating
        return None

    @property
    def allowed_activities(self):
        rated = [rating.activity for rating in self.leaderrating_set.all()]
        if rated:
            return rated + LeaderRating.OPEN_ACTIVITIES
        else:  # Not a MITOC leader, can't lead anything
            return []

    def can_lead(self, activity):
        if activity in LeaderRating.OPEN_ACTIVITIES:
            return True
        return self.leaderrating_set.filter(activity=activity).exists()

    @property
    def is_leader(self):
        """ Query ratings to determine if this participant is a leader.

        Wnen dealing with Users, it's faster to use utils.perms.is_leader
        """
        return self.leaderrating_set.exists()

    @property
    def email_addr(self):
        return '"{}" <{}>'.format(self.name, self.email)

    @property
    def info_current(self):
        since_last_update = timezone.now() - self.last_updated
        return since_last_update.days < settings.MUST_UPDATE_AFTER_DAYS

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ['name', 'email']


class LeaderRating(models.Model):
    """ A leader is just a participant with ratings for at least one activity type.

    The same personal + emergency information is required of leaders, but
    additional fields are present. So, we keep a Participant record for any
    leader. This makes it easy to check if any participant is a leader (just
    see `participant.ratings`) and easy to promote somebody to leader.

    It also allows leaders to function as participants (e.g. if a "SC" leader
    wants to go ice climbing).
    """
    # Activities where you must be rated in order to create/lead a trip
    BIKING = 'biking'
    BOATING = 'boating'
    CABIN = 'cabin'
    CLIMBING = 'climbing'
    HIKING = 'hiking'
    WINTER_SCHOOL = 'winter_school'
    CLOSED_ACTIVITY_CHOICES = [
            (BIKING, 'Biking'),
            (BOATING, 'Boating'),
            (CABIN, 'Cabin'),
            (CLIMBING, 'Climbing'),
            (HIKING, 'Hiking'),
            (WINTER_SCHOOL, 'Winter School'),
            ]
    CLOSED_ACTIVITIES = [val for (val, label) in CLOSED_ACTIVITY_CHOICES]

    # Activities for which a specific leader rating is not necessary
    # (You must be a MITOC leader, but not necessarily in these activities)
    CIRCUS = 'circus'
    OFFICIAL_EVENT = 'official_event'  # Training, films, etc.
    COURSE = 'course'
    OPEN_ACTIVITY_CHOICES = [
            (CIRCUS, 'Circus'),
            (OFFICIAL_EVENT, 'Official Event'),
            (COURSE, 'Course'),
            ]

    OPEN_ACTIVITIES = [val for (val, label) in OPEN_ACTIVITY_CHOICES]

    ACTIVITIES = CLOSED_ACTIVITIES + OPEN_ACTIVITIES
    ACTIVITY_CHOICES = CLOSED_ACTIVITY_CHOICES + OPEN_ACTIVITY_CHOICES

    participant = models.ForeignKey(Participant)
    activity = models.CharField(max_length='31',
                                choices=ACTIVITY_CHOICES)
    rating = models.CharField(max_length=31)
    notes = models.TextField(max_length=500, blank=True)  # Contingencies, etc.

    def __unicode__(self):
        return unicode(self.participant)

    class Meta:
        ordering = ["participant"]


class LeaderApplication(models.Model):
    # NOTE: Previous rating is needed during transition to new system
    # Leave ratings long for miscellaneous comments
    participant = models.OneToOneField(Participant)
    time_created = models.DateTimeField(auto_now_add=True)
    previous_rating = models.CharField(max_length=255, blank=True,
                                       help_text="Previous rating (if any)")
    desired_rating = models.CharField(max_length=255)

    taking_wfa = models.CharField(max_length=10,
                                  choices=[("Yes", "Yes"),
                                           ("No", "No"),
                                           ("Maybe", "Maybe/don't know")],
                                  verbose_name="Do you plan on taking the subsidized WFA at MIT?",
                                  help_text="Save $110 on the course fee by leading two or more trips!")
    training = models.TextField(blank=True, max_length=5000,
                                verbose_name="Formal training and qualifications",
                                help_text="Details of any medical, technical, or leadership training and qualifications relevant to the winter environment. State the approximate dates of these activities. Leave blank if not applicable.")
    winter_experience = models.TextField(blank=True, max_length=5000,
                                         help_text="Details of previous winter outdoors experience. Include the type of trip (x-country skiiing, above treeline, snowshoeing, ice climbing, etc), approximate dates and locations, numbers of participants, notable trail and weather conditions. Please also give details of whether you participated, lead, or co-lead these trips.")
    other_experience = models.TextField(blank=True, max_length=5000,
                                        verbose_name="Other outdoors/leadership experience",
                                        help_text="Details about any relevant non-winter experience")
    notes_or_comments = models.TextField(blank=True, max_length=5000,
                                         help_text="Any relevant details, such as any limitations on availability on Tue/Thurs nights or weekends during IAP.")

    def __unicode__(self):
        return "{}'s application".format(self.participant)

    class Meta:
        ordering = ["id"]


class BaseSignUp(models.Model):
    participant = models.ForeignKey(Participant)
    trip = models.ForeignKey("Trip")
    time_created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, max_length=1000)  # e.g. Answers to questions

    class Meta:
        abstract = True

    def __unicode__(self):
        return "{} on {}".format(self.participant.name, self.trip)


class LeaderSignUp(BaseSignUp):
    """ Represents a leader who has signed up to join a trip. """
    class Meta:
        ordering = ["time_created"]


class SignUp(BaseSignUp):
    """ An editable record relating a Participant to a Trip.

    The time of creation determines ordering in first-come, first-serve.
    """
    order = models.IntegerField(null=True, blank=True)  # As ranked by participant
    manual_order = models.IntegerField(null=True, blank=True)  # Order on trip

    on_trip = models.BooleanField(default=False)

    @property
    def other_signups(self):
        """ Return other relevant signups for this participant.

        The point of this property is to help leaders coordinate driving.
        """
        on_trips = self.__class__.objects.filter(on_trip=True,
                                                 participant=self.participant)
        others = on_trips.exclude(trip=self.trip)
        within_three_days = (self.trip.trip_date - timedelta(days=3),
                             self.trip.trip_date + timedelta(days=3))
        return others.filter(trip__trip_date__range=within_three_days)

    def save(self, **kwargs):
        """ Assert that the Participant is not signing up twice.

        The AssertionError here should never be thrown - it's a last defense
        against a less-than-obvious implementation of adding Participant
        records after getting a bound form.
        """
        if not kwargs.pop('commit', True):
            assert self.trip not in self.participant.trip_set.all()
        super(SignUp, self).save(**kwargs)

    class Meta:
        # When ordering for an individual, should order by priority (i.e. 'order')
        # When ordering for many, should go by time created.
        ordering = ["manual_order", "last_updated"]


class TripInfo(models.Model):
    drivers = models.ManyToManyField(Participant, blank=True,
                                     help_text=string_concat("If a trip participant is driving, but is not on this list, they must first submit <a href='",
                                                             reverse_lazy('edit_profile'),
                                                             "#car'>information about their car</a>. They should then be added here."))
    start_location = models.CharField(max_length=127)
    start_time = models.CharField(max_length=63)
    turnaround_time = models.CharField(max_length=63, blank=True,
                                       help_text="The time at which you'll turn back and head for your car/starting location")
    return_time = models.CharField(max_length=63, help_text="When you expect to return to your car/starting location and be able to call the WIMP")
    worry_time = models.CharField(max_length=63, help_text="Suggested: return time +3 hours. If the WIMP has not heard from you after this time and is unable to make contact with any leaders or participants, the authorities will be called.")
    itinerary = models.TextField(help_text="A detailed account of your trip plan. Where will you be going? What route will you be taking? "
                                           "Include trails, peaks, intermediate destinations, back-up plans- anything that would help rescuers find you.")


class Trip(models.Model):
    activity = models.CharField(max_length='31',
                                choices=LeaderRating.ACTIVITY_CHOICES,
                                default=LeaderRating.WINTER_SCHOOL)
    creator = models.ForeignKey(Participant, related_name='created_trips')
    # Leaders should be privileged at time of trip creation, but may no longer
    # be leaders later (and we don't want to break the relation)
    leaders = models.ManyToManyField(Participant, related_name='trips_led')
    allow_leader_signups = models.BooleanField(default=False,
                                               help_text="Allow leaders (with ratings for this activity) to sign themselves up for the trip any time before its date. Recommended for Circuses!")
    name = models.CharField(max_length=127)
    description = models.TextField()
    maximum_participants = models.PositiveIntegerField(default=8)
    difficulty_rating = models.CharField(max_length=63)
    level = models.CharField(max_length=255, help_text="This trip's A, B, or C designation (plus I/S rating if applicable).", null=True, blank=True)
    prereqs = models.CharField(max_length=255, blank=True)
    wsc_approved = models.BooleanField(default=False)
    notes = models.TextField(blank=True, max_length=2000,
                             help_text="Participants must add notes to their signups if you complete this field. "
                                       "This is a great place to ask important questions.")

    time_created = models.DateTimeField(auto_now_add=True)
    last_edited = models.DateTimeField(auto_now=True)
    trip_date = models.DateField(default=dateutils.nearest_sat)
    signups_open_at = models.DateTimeField(default=timezone.now)
    signups_close_at = models.DateTimeField(default=dateutils.wed_morning, null=True, blank=True)

    info = OptionalOneToOneField(TripInfo)

    signed_up_participants = models.ManyToManyField(Participant, through=SignUp)
    algorithm = models.CharField(max_length='31', default='lottery',
                                 choices=[('lottery', 'lottery'),
                                          ('fcfs', 'first-come, first-serve')])

    def __unicode__(self):
        return self.name

    @property
    def in_past(self):
        return self.trip_date < dateutils.local_now().date()

    @property
    def after_lottery(self):
        """ True if it's after the lottery, but takes place before the next one. """
        # Assumes lotteries take place at same time. Should be 'good enough'
        next_lottery = dateutils.next_lottery()
        past_lottery = dateutils.lottery_time(next_lottery - timedelta(days=7))

        return (dateutils.local_now() > past_lottery and
                self.midnight_before < next_lottery)

    @property
    def midnight_before(self):
        return pytz_timezone.localize(dateutils.midnight_before(self.trip_date))

    @property
    def open_slots(self):
        accepted_signups = self.signup_set.filter(on_trip=True)
        return self.maximum_participants - accepted_signups.count()

    @property
    def signups_open(self):
        passed_signup_date = (timezone.now() > self.signups_open_at)
        return passed_signup_date and not self.signups_closed

    @property
    def signups_closed(self):
        """ If a close time is given, return if that time is passed. """
        return self.signups_close_at and timezone.now() > self.signups_close_at

    @property
    def signups_not_yet_open(self):
        """ True if signups open at some point in the future, else False. """
        return timezone.now() < self.signups_open_at

    @property
    def last_of_priority(self):
        """ The 'manual_order' value for a signup to be priority, but below others.

        That is, leader-ordered signups should go above other signups. (Let's
        say that a leader is organizing signups, but new signups come in before
        they submit the ordering - we want to be sure all their ordering goes
        above any new signups).
        """
        last_signup = self.signup_set.last()
        min_order = last_signup.manual_order or 0
        return min_order + 1

    def make_fcfs(self, signups_open_at=None):
        """ Set the algorithm to FCFS, adjust signup times appropriately. """
        self.algorithm = 'fcfs'
        now = dateutils.local_now()
        if signups_open_at:
            self.signups_open_at = signups_open_at
        elif dateutils.wed_morning() <= now < dateutils.closest_wed_at_noon():
            # If posted between lottery time and noon, make it open at noon
            self.signups_open_at = dateutils.closest_wed_at_noon()
        else:
            self.signups_open_at = now
        self.signups_close_at = self.midnight_before

    def clean(self):
        """ Ensure that all trip dates are reasonable. """
        if not self.time_created:  # Trip first being created
            if self.after_lottery:
                self.make_fcfs()
            if self.signups_closed:
                raise ValidationError("Signups can't be closed already!")
            # Careful here - don't want to disallow editing of past trips
            if self.trip_date < dateutils.local_now().date():
                raise ValidationError("Trips can't occur in the past!")

        close_time = self.signups_close_at
        if close_time and close_time < self.signups_open_at:
            raise ValidationError("Trips cannot open after they close.")

    def leaders_with_rating(self):
        for leader in self.leaders.all():
            yield leader.name_with_rating(self.activity)

    class Meta:
        ordering = ["-trip_date", "-time_created"]


class BygonesManager(models.Manager):
    def get_queryset(self):
        feedback = super(BygonesManager, self).get_queryset()
        fuggedaboutit = dateutils.local_now() - timedelta(days=390)

        return feedback.exclude(trip__trip_date__lt=fuggedaboutit)


class Feedback(models.Model):
    """ Feedback given for a participant on one trip. """
    objects = BygonesManager()  # By default, ignore feedback older than ~13 months
    everything = models.Manager()  # But give the option to look at older feedback

    participant = models.ForeignKey(Participant)
    leader = models.ForeignKey(Participant, related_name="authored_feedback")
    showed_up = models.BooleanField(default=True)
    comments = models.TextField(max_length=2000)
    # Allows general feedback (i.e. not linked to a trip)
    trip = models.ForeignKey(Trip, null=True, blank=True)
    time_created = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        return '{}: "{}" - {}'.format(self.participant, self.comments, self.leader)

    class Meta:
        ordering = ["participant", "-time_created"]


class LotteryInfo(models.Model):
    """ Persists from week-to-week, but can be changed. """
    participant = models.OneToOneField(Participant)
    car_status = models.CharField(max_length=7,
                                  choices=[("none", "No car"),
                                           ("own", "Can drive own car"),
                                           ("rent", "Willing to rent")],
                                  default="none")
    number_of_passengers = models.PositiveIntegerField(null=True, blank=True,
                                                       validators=[MaxValueValidator(13, message="Do you drive a bus?")])
    last_updated = models.DateTimeField(auto_now=True)
    paired_with = models.ForeignKey(Participant, null=True, blank=True,
                                    related_name='paired_by')

    @property
    def is_driver(self):
        return self.car_status in ['own', 'rent']

    def clean(self):
        # Renters might not yet know number of passengers
        if self.car_status == 'own' and not self.number_of_passengers:
            raise ValidationError("How many passengers can you bring?")

    class Meta:
        ordering = ["car_status", "number_of_passengers"]


class WaitListSignup(models.Model):
    """ Intermediary between initial signup and the trip's waiting list. """
    signup = models.OneToOneField(SignUp)
    waitlist = models.ForeignKey("WaitList")
    time_created = models.DateTimeField(auto_now_add=True)
    # Specify to override ordering by time created
    manual_order = models.IntegerField(null=True, blank=True)

    def __unicode__(self):
        return "{} waitlisted on {}".format(self.signup.participant.name,
                                            self.signup.trip)

    class Meta:
        # None will come after after integer in reverse sorted,
        # So anyone with a manual ordering integer will be first
        ordering = ["-manual_order", "time_created"]


class WaitList(models.Model):
    """ Treat the waiting list as a simple FIFO queue. """
    trip = models.OneToOneField(Trip)
    unordered_signups = models.ManyToManyField(SignUp, through=WaitListSignup)

    @property
    def signups(self):
        # Don't know of any way to apply this ordering to signups field
        return self.unordered_signups.order_by('waitlistsignup')

    @property
    def first_of_priority(self):
        """ The 'manual_order' value to be first in the waitlist. """
        first_wl_signup = self.waitlistsignup_set.first()
        max_order = first_wl_signup.manual_order or 9  # Could be None
        return max_order + 1

    @property
    def last_of_priority(self):
        """ The 'manual_order' value to be priority, but below others. """
        last_wl_signup = self.waitlistsignup_set.last()
        min_order = last_wl_signup.manual_order or 11  # Could be None
        return min_order - 1
