from datetime import date
from textwrap import dedent
from unittest import mock

from bs4 import BeautifulSoup
from django.core import mail
from django.test import TestCase
from freezegun import freeze_time

from ws.email import renew
from ws.tests.factories import DiscountFactory, ParticipantFactory


@freeze_time("2020-01-12 09:00:00 EST")
class RenewTest(TestCase):
    def test_will_not_email_without_membership(self):
        par = ParticipantFactory.create(membership=None)

        with mock.patch.object(mail.EmailMultiAlternatives, 'send') as send:
            with self.assertRaises(ValueError) as cm:
                renew.send_email_reminding_to_renew(par)
        send.assert_not_called()

        self.assertIn('no membership on file', str(cm.exception))

    def test_will_not_email_if_already_expired(self):
        par = ParticipantFactory.create(
            membership__membership_expires=date(2020, 1, 10)
        )

        with mock.patch.object(mail.EmailMultiAlternatives, 'send') as send:
            with self.assertRaises(ValueError) as cm:
                renew.send_email_reminding_to_renew(par)
        send.assert_not_called()

        self.assertIn('Membership has already expired', str(cm.exception))

    def test_will_not_email_if_only_signed_waiver(self):
        par = ParticipantFactory.create(
            membership__membership_expires=None,
            membership__waiver_expires=date(2018, 1, 1),
        )

        with mock.patch.object(mail.EmailMultiAlternatives, 'send') as send:
            with self.assertRaises(ValueError) as cm:
                renew.send_email_reminding_to_renew(par)
        send.assert_not_called()

        self.assertIn('no membership on file', str(cm.exception))

    def test_will_not_email_before_renewal_date(self):
        par = ParticipantFactory.create(
            # 2 months left is *nearly* expiring, but not yet within the window
            membership__membership_expires=date(2020, 3, 13),
        )

        with mock.patch.object(mail.EmailMultiAlternatives, 'send') as send:
            with self.assertRaises(ValueError) as cm:
                renew.send_email_reminding_to_renew(par)
        send.assert_not_called()

        self.assertIn("don't yet recommend renewal", str(cm.exception))

    def test_normal_renewal_no_discounts(self):
        par = ParticipantFactory.create(
            # Nearly expiring, less than a month to go.
            membership__membership_expires=date(2020, 2, 5)
        )

        with mock.patch.object(mail.EmailMultiAlternatives, 'send') as send:
            msg = renew.send_email_reminding_to_renew(par)
        send.assert_called_once()

        expected_text = dedent(
            """
            Your MITOC membership will expire on February 5, 2020.

            Renew today to add another 365 days to your membership:
            https://https://mitoc-trips.mit.edu/profile/membership/

            Renewing any time between now and February 5th
            will ensure that your membership is valid until February 4, 2021.

            Your MITOC membership enables you to:
            - rent gear from the MITOC office
            - enroll in discounts for club members
            - go on official trips
            - stay in MITOC's cabins

            ----------------------------------------------------------------------------

            You can unsubscribe from membership renewal reminders, but note that we send
            at most one reminder per year: we will not email you again unless you renew.

            https://mitoc-trips.mit.edu/preferences/email/

            Questions? Contact us: https://mitoc-trips.mit.edu/contact/
            """
        )
        self.assertEqual(msg.body, expected_text)

    def test_participant_with_discounts(self):
        """We mention a participant's discounts when offering renewal."""
        par = ParticipantFactory.create(membership__membership_expires=date(2020, 2, 5))
        par.discounts.add(DiscountFactory.create(name="Zazu's Advisory Services"))
        par.discounts.add(DiscountFactory.create(name='Acme Corp'))

        with mock.patch.object(mail.EmailMultiAlternatives, 'send') as send:
            msg = renew.send_email_reminding_to_renew(par)
        send.assert_called_once()

        expected_text = dedent(
            """
            Your MITOC membership will expire on February 5, 2020.

            Renewing is required to maintain access to your discounts with:
            - Acme Corp
            - Zazu's Advisory Services

            Renew today to add another 365 days to your membership:
            https://https://mitoc-trips.mit.edu/profile/membership/

            Renewing any time between now and February 5th
            will ensure that your membership is valid until February 4, 2021.

            Your MITOC membership enables you to:
            - rent gear from the MITOC office
            - enroll in discounts for club members
            - go on official trips
            - stay in MITOC's cabins

            ----------------------------------------------------------------------------

            You can unsubscribe from membership renewal reminders, but note that we send
            at most one reminder per year: we will not email you again unless you renew.

            https://mitoc-trips.mit.edu/preferences/email/

            Questions? Contact us: https://mitoc-trips.mit.edu/contact/
            """
        )
        self.assertEqual(msg.body, expected_text)

        html, mime_type = msg.alternatives[0]
        self.assertEqual(mime_type, 'text/html')
        soup = BeautifulSoup(html, 'html.parser')
        self.assertEqual(
            [tag.attrs['href'] for tag in soup.find_all('a')],
            [
                # We link to the discounts immediately, since that's mentioned up-front
                'https://mitoc.mit.edu/preferences/discounts/',
                'https://https://mitoc-trips.mit.edu/profile/membership/',
                'https://mitoc.mit.edu/rentals',
                # All MITOCers are told about discounts in their renewal email
                'https://mitoc.mit.edu/preferences/discounts/',
                'https://mitoc-trips.mit.edu/trips/',
                'https://mitoc.mit.edu/rentals/cabins',
                'https://mitoc-trips.mit.edu/preferences/email/',
                'https://mitoc-trips.mit.edu/contact/',
            ],
        )
