from __future__ import unicode_literals

from django.contrib.auth.models import User
from django.db import models

from localflavor.us.models import PhoneNumberField
from ws.fields import OptionalOneToOneField
from localflavor.us.models import USStateField


class Car(models.Model):
    license_plate = models.CharField(max_length=7)
    state = USStateField()
    make = models.CharField(max_length=63)
    model = models.CharField(max_length=63)
    year = models.IntegerField()


class Person(models.Model):
    """ All individuals require a name, email, and (optionally) a cell. """
    name = models.CharField(max_length=255)
    cell_phone = PhoneNumberField(null=True, blank=True)  # Hi, Sheep.

    class Meta:
        abstract = True


class EmergencyContact(Person):
    relationship = models.CharField(max_length=63)
    email = models.EmailField()


class EmergencyInfo(models.Model):
    emergency_contact = models.OneToOneField(EmergencyContact)
    allergies = models.CharField(max_length=255, blank=True)
    medications = models.CharField(max_length=255, blank=True)
    medical_history = models.TextField(blank=True, help_text="Anything your trip leader would want to know about.")


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
    trips_attended = models.ManyToManyField('Trip')


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


class Trip(models.Model):
    creator = models.ForeignKey(Leader, related_name='created_trips')
    leaders = models.ManyToManyField(Leader)
    name = models.CharField(max_length=127)
    description = models.TextField()
    time_created = models.DateTimeField(auto_now_add=True)
    last_edited = models.DateTimeField(auto_now=True)
    trip_date = models.DateField()
    capacity = models.IntegerField()
    leaders_willing_to_rent = models.BooleanField(default=False)
    difficulty_rating = models.CharField(max_length=127)
    prereqs = models.CharField(max_length=255)  # one line; to be used during trip signups
    wsc_approved = models.BooleanField(default=False)

    #participants (ordered list w/ waiting list)
    algorithm = models.CharField(max_length='31',
                                 choices=[('lottery', 'lottery'),
                                          ('fcfs', 'first-come, first-serve')])


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
