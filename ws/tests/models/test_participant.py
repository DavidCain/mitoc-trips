import datetime

import ws.utils.dates as dateutils
from ws.tests import TestCase, factories


class ProblemsWithProfile(TestCase):
    # NOTE: These require TestCase since we do actual db lookups based on the record
    def test_our_factory_is_okay(self):
        """ The participant factory that we use is expected to have no problems. """
        participant = factories.ParticipantFactory.create()
        self.assertFalse(participant.problems_with_profile)

    def test_no_cell_phone_on_emergency_contact(self):
        participant = factories.ParticipantFactory.create()
        e_contact = factories.EmergencyContactFactory.create(cell_phone='')
        participant.emergency_info.emergency_contact = e_contact
        participant.save()

        self.assertEqual(
            participant.problems_with_profile,
            ["Please supply a valid number for your emergency contact."],
        )

    def test_full_name_required(self):
        participant = factories.ParticipantFactory.create(name='Cher')
        self.assertEqual(
            participant.problems_with_profile, ["Please supply your full legal name."]
        )

    def test_verified_email_required(self):
        participant = factories.ParticipantFactory.create()

        # Directly assign the participant an invalid email
        # (this should never happen, since we enforce that addresses come from user.emailaddress_set)
        participant.email = 'not-verified@example.com'

        self.assertEqual(
            participant.problems_with_profile,
            [
                'Please <a href="/accounts/email/">verify that you own not-verified@example.com</a>, '
                'or set your email address to one of your verified addresses.'
            ],
        )

    def test_xss_on_email_prevented(self):
        """ Returned strings can be trusted as HTML. """
        participant = factories.ParticipantFactory.create(
            email="</a><script>alert('hax')</script>@hacks.tld"
        )

        participant.user.emailaddress_set.update(verified=False)
        self.assertEqual(
            participant.user.emailaddress_set.get().email,  # (our factory assigns only one email)
            "</a><script>alert('hax')</script>@hacks.tld",
        )

        self.assertEqual(
            participant.problems_with_profile,
            [
                'Please <a href="/accounts/email/">verify that you own '
                # Note the HTML escaping!
                '&lt;/a&gt;&lt;script&gt;alert(&#39;hax&#39;)&lt;/script&gt;@hacks.tld</a>, '
                'or set your email address to one of your verified addresses.'
            ],
        )

    def test_old_student_affiliation_dated(self):
        student = factories.ParticipantFactory.create(affiliation='S')  # MIT or not?

        self.assertEqual(
            student.problems_with_profile, ["Please update your MIT affiliation."]
        )

    def test_not_updated_since_affiliation_overhaul(self):
        """ Any participant with affiliation predating our new categories should re-submit! """
        # This is right before the time when we released new categories!
        before_cutoff = dateutils.localize(datetime.datetime(2018, 10, 27, 3, 15))

        # Override the default "now" timestamp, to make participant's last profile update look old
        participant = factories.ParticipantFactory.create()
        participant.profile_last_updated = before_cutoff
        participant.save()

        self.assertEqual(
            participant.problems_with_profile, ["Please update your MIT affiliation."]
        )
