from __future__ import unicode_literals

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.validators import RegexValidator
from django.db import models
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from localflavor.us.models import PhoneNumberField
from localflavor.us.models import USStateField
from ws.fields import OptionalOneToOneField
from ws.dateutils import nearest_sat, wed_morning, local_now


class SassyMax(MaxValueValidator):
    message = "Do you drive a bus?..."  # Can set as param in Django 1.8


alphanum = RegexValidator(r'^[a-zA-Z0-9 ]*$',
                          "Only alphanumeric characters and spaces allowed")


class Car(models.Model):
    # As long as this module is reloaded once a year, this is fine
    # (First license plates were issued in Mass in 1903)
    year_min, year_max = 1903, local_now().year + 2
    # Loosely validate - may wish to use international plates in the future
    license_plate = models.CharField(max_length=31, validators=[alphanum])
    state = USStateField()
    make = models.CharField(max_length=63)
    model = models.CharField(max_length=63)
    year = models.PositiveIntegerField(max_length=4,
                                       validators=[MaxValueValidator(year_max),
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


class Participant(models.Model):
    """ Anyone going on a trip needs WIMP info, and info about their car.

    Even leaders will have a Participant record (see docstring of Leader)
    """
    name = models.CharField(max_length=255)
    cell_phone = PhoneNumberField(null=True, blank=True)  # Hi, Sheep.
    last_updated = models.DateTimeField(auto_now=True)
    user = models.OneToOneField(User)
    emergency_info = models.OneToOneField(EmergencyInfo)
    email = models.EmailField(unique=True)
    car = OptionalOneToOneField(Car)
    affiliation = models.CharField(max_length=1,
                                   choices=[('S', "MIT student"),
                                            ('M', "MIT affiliate"),
                                            ('N', "Non-affiliate")])
    attended_lectures = models.BooleanField(default=False)

    @property
    def email_addr(self):
        return '"{}" <{}>'.format(self.name, self.email)

    @property
    def info_current(self):
        since_last_update = timezone.now() - self.last_updated
        return since_last_update.days < settings.MUST_UPDATE_AFTER_DAYS

    def __unicode__(self):
        try:
            is_leader = self.leader
        except ObjectDoesNotExist:
            return self.name
        else:
            return "{} ({})".format(self.name, self.leader.rating)

    class Meta:
        ordering = ['name', 'email']


class Leader(models.Model):
    """ A Leader is a special participant (just one with extra privileges).

    This is acheived by pointing to a participant object.

    The same personal + emergency information is required of leaders, but
    additional fields are present. So, we keep a Participant record for any
    leader. This makes it easy to check if any participant is a leader (just
    see `participant.leader`), easy to promote somebody to leader (just make a
    new leader record, point to their old participant record, etc.)

    It also allows leaders to function as participants (e.g. if a "SC" leader
    wants to go ice climbing).
    """
    participant = models.OneToOneField(Participant)
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


class SignUp(models.Model):
    """ An editable record relating a Participant to a Trip.

    The time of creation determines ordering in first-come, first-serve.
    """
    participant = models.ForeignKey(Participant)
    trip = models.ForeignKey("Trip")
    time_created = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, max_length=1000)  # e.g. Answers to questions
    order = models.IntegerField(null=True, blank=True)

    on_trip = models.BooleanField(default=False)

    def save(self, **kwargs):
        """ Assert that the Participant is not signing up twice.

        The AssertionError here should never be thrown - it's a last defense
        against a less-than-obvious implementation of adding Participant
        records after getting a bound form.
        """
        if not kwargs.pop('commit', True):
            assert self.trip not in self.participant.trip_set.all()
        super(SignUp, self).save(**kwargs)

    def clean(self):
        """ Trip must be open, notes only required if the trip has notes. """
        try:
            trip = self.trip
        except ObjectDoesNotExist:
            pass  # A missing trip will be caught
        else:
            if trip.notes and not self.notes:
                raise ValidationError("Please complete notes to sign up!")
            if not trip.signups_open:
                # Interface shouldn't allow this, but a clever person
                # could try to POST data.  No harm in making sure...
                raise ValidationError("Signups aren't open for this trip!")

    def __unicode__(self):
        return "{} on {}".format(self.participant.name, self.trip)

    class Meta:
        # When ordering for an individual, should order by priority (i.e. 'order')
        # When ordering for many, should go by time created.
        ordering = ["time_created"]


class Trip(models.Model):
    creator = models.ForeignKey(Leader, related_name='created_trips')
    leaders = models.ManyToManyField(Leader)
    name = models.CharField(max_length=127)
    description = models.TextField()
    maximum_participants = models.PositiveIntegerField(default=8)
    difficulty_rating = models.CharField(max_length=127)
    prereqs = models.CharField(max_length=255, blank=True)
    wsc_approved = models.BooleanField(default=False)
    notes = models.TextField(blank=True, max_length=2000)

    time_created = models.DateTimeField(auto_now_add=True)
    last_edited = models.DateTimeField(auto_now=True)
    trip_date = models.DateField(default=nearest_sat)
    signups_open_at = models.DateTimeField(default=timezone.now)
    signups_close_at = models.DateTimeField(default=wed_morning, null=True, blank=True)

    signed_up_participants = models.ManyToManyField(Participant, through=SignUp)
    algorithm = models.CharField(max_length='31', default='lottery',
                                 choices=[('lottery', 'lottery'),
                                          ('fcfs', 'first-come, first-serve')])

    def __unicode__(self):
        return self.name

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

    def clean(self):
        """ Ensure that all trip dates are reasonable. """
        close_time = self.signups_close_at
        if close_time and close_time < self.signups_open_at:
            raise ValidationError("Trips cannot open after they close.")

        if not self.time_created:  # Trip first being created
            if self.signups_closed:
                raise ValidationError("Signups can't be closed already!")
            # Careful here - don't want to disallow editing of past trips
            if self.trip_date < local_now().date():
                raise ValidationError("Trips can't occur in the past!")

    class Meta:
        ordering = ["-trip_date", "-time_created"]


class Feedback(models.Model):
    """ Feedback given for a participant on one trip. """
    participant = models.ForeignKey(Participant)
    showed_up = models.BooleanField(default=True)
    comments = models.TextField(max_length=2000)
    leader = models.ForeignKey(Leader)
    # Allows general feedback (i.e. not linked to a trip)
    trip = models.ForeignKey(Trip, null=True, blank=True)
    time_created = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        return '{}: "{}" - {}'.format(self.participant, self.comments, self.leader)

    class Meta:
        ordering = ["participant", "time_created"]


class LotteryInfo(models.Model):
    """ Persists from week-to-week, but can be changed. """
    participant = models.OneToOneField(Participant)
    car_status = models.CharField(max_length=7,
                                  choices=[("none", "No car"),
                                           ("own", "Can drive own car"),
                                           ("rent", "Willing to rent")],
                                  default="none")
    number_of_passengers = models.PositiveIntegerField(null=True, blank=True,
                                                       validators=[SassyMax(13)])
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
