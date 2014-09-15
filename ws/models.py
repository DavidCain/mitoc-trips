from __future__ import unicode_literals

from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from localflavor.us.models import PhoneNumberField
from localflavor.us.models import USStateField
from ws.fields import OptionalOneToOneField
from ws.dateutils import nearest_sat, wed_at_noon


class Car(models.Model):
    license_plate = models.CharField(max_length=7)
    state = USStateField()
    make = models.CharField(max_length=63)
    model = models.CharField(max_length=63)
    year = models.IntegerField()
    color = models.CharField(max_length=63)

    def __unicode__(self):
        car_info = "{} {} {} {}".format(self.color, self.year, self.make, self.model)
        registration_info = "-".join([self.license_plate, self.state])
        return "{} ({})".format(car_info, registration_info)


class Person(models.Model):
    """ All individuals require a name, email, and (optionally) a cell. """
    name = models.CharField(max_length=255)
    cell_phone = PhoneNumberField(null=True, blank=True)  # Hi, Sheep.

    class Meta:
        abstract = True
        ordering = ["name"]


class EmergencyContact(Person):
    relationship = models.CharField(max_length=63)
    email = models.EmailField()

    def __unicode__(self):
        return "{} ({}): {}".format(self.name, self.relationship, self.cell_phone)


class EmergencyInfo(models.Model):
    emergency_contact = models.OneToOneField(EmergencyContact)
    allergies = models.CharField(max_length=255, blank=True)
    medications = models.CharField(max_length=255, blank=True)
    medical_history = models.TextField(blank=True, help_text="Anything your trip leader would want to know about.")

    def __unicode__(self):
        return ("Allergies: {} | Medications: {} | History: {} | "
                "Contact: {}".format(self.allergies, self.medications,
                                     self.medical_history, self.emergency_contact))


class Participant(Person):
    """ Anyone going on a trip needs WIMP info, and info about their car.

    Even leaders will have a Participant record (see docstring of Leader)
    """
    last_updated = models.DateTimeField(auto_now=True)
    user = models.OneToOneField(User)
    emergency_info = models.OneToOneField(EmergencyInfo)
    email = models.EmailField(unique=True)
    car = OptionalOneToOneField(Car)
    affiliation = models.CharField(max_length=1,
                                   choices=[("S", "Student"),
                                            ("M", "MIT affiliate"),
                                            ("N", "Non-affiliate")])
    attended_lectures = models.BooleanField(default=False)

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
    rating = models.CharField(max_length=255)  # Leave long for comments about rating

    def __unicode__(self):
        return unicode(self.participant)

    class Meta:
        ordering = ["participant"]


class SignUp(models.Model):
    """ An editable record relating a Participant to a Trip.

    The time of creation determines ordering in first-come, first-serve.
    """
    participant = models.ForeignKey(Participant)
    trip = models.ForeignKey("Trip")
    time_created = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)  # e.g. Answers to questions
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
        ordering = ["order", "time_created"]


class Trip(models.Model):
    creator = models.ForeignKey(Leader, related_name='created_trips')
    leaders = models.ManyToManyField(Leader)
    name = models.CharField(max_length=127)
    description = models.TextField()
    capacity = models.PositiveIntegerField(default=10)
    leaders_willing_to_rent = models.BooleanField(default=False)
    difficulty_rating = models.CharField(max_length=127)
    prereqs = models.CharField(max_length=255, blank=True)
    wsc_approved = models.BooleanField(default=False)  # TODO: What if trip changes?
    notes = models.TextField(blank=True)

    time_created = models.DateTimeField(auto_now_add=True)
    last_edited = models.DateTimeField(auto_now=True)
    trip_date = models.DateField(default=nearest_sat)
    signups_open_at = models.DateTimeField(default=datetime.now)
    signups_close_at = models.DateTimeField(default=wed_at_noon, null=True, blank=True)

    signed_up_participants = models.ManyToManyField(Participant, through=SignUp)
    algorithm = models.CharField(max_length='31', default='lottery',
                                 choices=[('lottery', 'lottery'),
                                          ('fcfs', 'first-come, first-serve')])

    def __unicode__(self):
        return self.name

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

        if self.signups_closed:
            raise ValidationError("Signups can't be closed already!")
        if not self.time_created:  # Trip first being created
            # Careful here - don't want to disallow editing of past trips
            if self.trip_date < datetime.now().date():
                raise ValidationError("Trips can't occur in the past!")

    class Meta:
        ordering = ["-trip_date"]


class Feedback(models.Model):
    """ Feedback given for a participant on one trip. """
    participant = models.ForeignKey(Participant)
    showed_up = models.BooleanField(default=True)
    comments = models.TextField()
    leader = models.ForeignKey(Leader)
    prefer_anonymous = models.BooleanField(default=False)
    # Allows general feedback (i.e. not linked to a trip)
    trip = models.ForeignKey(Trip, null=True, blank=True)
    time_created = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        author = "anonymous" if self.prefer_anonymous else self.leader
        return '{}: "{}" - {}'.format(self.participant, self.comments, author)

    class Meta:
        ordering = ["participant", "time_created"]


class LotteryInfo(models.Model):
    """ Persists from week-to-week, but can be changed. """
    participant = models.OneToOneField(Participant)
    own_a_car = models.BooleanField(default=False)
    willing_to_rent = models.BooleanField(default=False)
    number_of_passengers = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["own_a_car", "willing_to_rent", "number_of_passengers"]
