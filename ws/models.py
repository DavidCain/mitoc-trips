from __future__ import unicode_literals

#from django.core.exceptions import ValidationError
#from django.core.validators import RegexValidator
from django.db import models

from phonenumber_field.modelfields import PhoneNumberField


class OptionalOneToOneField(models.OneToOneField):
    """ One-to-one relationships in schema can (and often will be) null. """
    def __init__(self, *args, **kwargs):
        null = kwargs.pop('null', True)
        blank = kwargs.pop('blank', True)
        super(OptionalOneToOneField, self).__init__(*args, null=null, blank=blank, **kwargs)


class Car(models.Model):
    license_plate = models.CharField(max_length=7)
    make = models.CharField(max_length=63)
    model = models.CharField(max_length=63)
    year = models.IntegerField()


class Person(models.Model):
    """ All individuals require a name, email, and (optionally) a cell. """
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    cell_phone = PhoneNumberField(null=True, blank=True)  # Hi, Sheep.

    class Meta:
        abstract = True


class EmergencyContact(Person):
    relationship = models.CharField(max_length=63)


class TripGoer(Person):
    """ Anyone going on a trip needs WIMP info, and info about their car. """
    emergency_contact = models.OneToOneField(EmergencyContact)
    car = OptionalOneToOneField(Car)

    class Meta(Person.Meta):
        abstract = True


class Leader(TripGoer):
    rating = models.CharField(max_length=255)  # Leave long for comments about rating
    car = OptionalOneToOneField(Car)


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


class Participant(TripGoer):
    affiliation = models.CharField(max_length=1,
                                   choices=[("S", "Student"),
                                            ("M", "MIT affiliate"),
                                            ("N", "Non-affiliate")])
    attended_lectures = models.BooleanField(default=False)
    trips_attended = models.ManyToManyField('Trip')


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
