from datetime import date
from textwrap import dedent
from unittest import mock

from django.core import mail
from django.test import TestCase
from freezegun import freeze_time

from ws.email import renew
from ws.tests.factories import ParticipantFactory


@freeze_time("2020-01-12 09:00:00 EST")
class RenewTest(TestCase):
    maxDiff = None

    def test_will_not_email_without_membership(self) -> None:
        par = ParticipantFactory.create(membership=None)

        with mock.patch.object(mail.EmailMultiAlternatives, "send") as send:
            with self.assertRaises(ValueError) as cm:
                renew.send_email_reminding_to_renew(par)
        send.assert_not_called()

        self.assertIn("no membership on file", str(cm.exception))

    def test_will_not_email_if_already_expired(self) -> None:
        par = ParticipantFactory.create(
            membership__membership_expires=date(2020, 1, 10)
        )

        with mock.patch.object(mail.EmailMultiAlternatives, "send") as send:
            with self.assertRaises(ValueError) as cm:
                renew.send_email_reminding_to_renew(par)
        send.assert_not_called()

        self.assertIn("Membership has already expired", str(cm.exception))

    def test_will_not_email_if_only_signed_waiver(self) -> None:
        par = ParticipantFactory.create(
            membership__membership_expires=None,
            membership__waiver_expires=date(2018, 1, 1),
        )

        with mock.patch.object(mail.EmailMultiAlternatives, "send") as send:
            with self.assertRaises(ValueError) as cm:
                renew.send_email_reminding_to_renew(par)
        send.assert_not_called()

        self.assertIn("no membership on file", str(cm.exception))

    def test_will_not_email_before_renewal_date(self) -> None:
        par = ParticipantFactory.create(
            # 2 months left is *nearly* expiring, but not yet within the window
            membership__membership_expires=date(2020, 3, 13),
        )

        with mock.patch.object(mail.EmailMultiAlternatives, "send") as send:
            with self.assertRaises(ValueError) as cm:
                renew.send_email_reminding_to_renew(par)
        send.assert_not_called()

        self.assertIn("don't yet recommend renewal", str(cm.exception))

    def test_normal_renewal(self) -> None:
        par = ParticipantFactory.create(
            # Exact token depends on the participant's PK
            pk=881203,
            # Nearly expiring, less than a month to go.
            membership__membership_expires=date(2020, 2, 5),
        )

        with mock.patch.object(mail.EmailMultiAlternatives, "send") as send:
            with self.settings(UNSUBSCRIBE_SECRET_KEY="sooper-secret"):  # noqa: S106
                msg = renew.send_email_reminding_to_renew(par)
        send.assert_called_once()

        expected_text = dedent(
            """
            Your MITOC membership will expire on February 5, 2020.

            Renew today to add another 365 days to your membership:
            https://mitoc-trips.mit.edu/profile/membership/

            Renewing any time between now and February 5th
            will ensure that your membership is valid until February 4, 2021.

            Your MITOC membership enables you to:
            - rent gear from the MITOC office
            - go on official trips
            - stay in MITOC's cabins

            ------------------------------------------------------

            You can unsubscribe from membership renewal reminders:
            https://mitoc-trips.mit.edu/preferences/email/eyJwayI6ODgxMjAzLCJlbWFpbHMiOlswXX0:1iqdma:E21Brio4e9XNfaBVGCSvSnEVo5CQX9mcUcuUAyL_dSw/

            Note that we send at most one reminder per year:
            we will not email you again unless you renew.

            You can also manage your email preferences directly:
            https://mitoc-trips.mit.edu/preferences/email/

            Questions? Contact us: https://mitoc-trips.mit.edu/contact/
            """
        )
        self.assertEqual(msg.body, expected_text)
