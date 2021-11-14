from django.core import signing
from django.core.signing import TimestampSigner
from django.test import SimpleTestCase
from freezegun import freeze_time

from ws import unsubscribe
from ws.tests import TestCase, factories


@freeze_time("2021-12-10 12:00:00 EST")
class UnsubscribeTest(SimpleTestCase):  # no db access, but uses self.settings
    def test_generate_token(self):
        par = factories.ParticipantFactory.build(pk=22)
        token = unsubscribe.generate_unsubscribe_token(par)
        # A bit circular, but show that we extract the signed data
        self.assertEqual(
            unsubscribe.unsign_token(token),
            (22, {unsubscribe.EmailType.membership_renewal}),
        )

    def test_expired_token(self):
        """Tokens are only valid for so long."""
        par = factories.ParticipantFactory.build(pk=22)
        with freeze_time("2021-09-01 12:00:00 EST"):
            token = unsubscribe.generate_unsubscribe_token(par)
            self.assertEqual(unsubscribe.unsign_token(token).participant_pk, 22)

        # 28 days later, still works
        with freeze_time("2021-09-29 12:00:00 EST"):
            self.assertEqual(unsubscribe.unsign_token(token).participant_pk, 22)

        # >30 days later, expired
        with freeze_time("2021-10-03 12:00:00 EST"):
            with self.assertRaises(signing.SignatureExpired):
                unsubscribe.unsign_token(token)

    def test_read_old_token(self):
        """We can read tokens that are moderately old, so long as they're < 30 days."""
        token = 'eyJwayI6MzcsImVtYWlscyI6WzBdfQ:1mmJT8:hXpCFBUrqIKOKPKEAEOrYBG4tm608r16HzFGKLJzhnA'

        with self.settings(UNSUBSCRIBE_SECRET_KEY='sooper-secret'):
            par_pk, email_types = unsubscribe.unsign_token(token)
        self.assertEqual(par_pk, 37)
        self.assertEqual(email_types, {unsubscribe.EmailType.membership_renewal})

    def test_must_have_correct_secret(self):
        token = 'eyJwayI6MzcsImVtYWlscyI6WzBdfQ:1mmJT8:hXpCFBUrqIKOKPKEAEOrYBG4tm608r16HzFGKLJzhnA'

        with self.settings(UNSUBSCRIBE_SECRET_KEY='sooper-secret'):
            unsubscribe.unsign_token(token)

        with self.settings(UNSUBSCRIBE_SECRET_KEY='changed-the-secret'):
            with self.assertRaises(signing.BadSignature):
                unsubscribe.unsign_token(token)

    def test_tokens_are_salted(self):
        """We use a namespaced salt to avoid token re-use.

        This test is a bit circular in nature, but mostly is documentation as
        to *why* we're using the same salt for all participants (feels a bit weird).

        # > Using salt in this way puts the different signatures into different
        # > namespaces. A signature that comes from one namespace (a particular salt
        # > value) cannot be used to validate the same plaintext string in a different
        # > namespace that is using a different salt setting.

        https://docs.djangoproject.com/en/3.2/topics/signing/

        We *could* use a nonce to avoid re-used the same tokens, but there's no real
        reason these tokens can't be shown again and again.
        """

        def _sha_256_signed(payload, salt, key='sooper-secret') -> str:
            signer = TimestampSigner(key=key, salt=salt, algorithm='sha256')
            return signer.sign_object(payload)

        par = factories.ParticipantFactory.build(pk=22)
        payload = {'pk': 22, 'emails': [0]}

        with self.settings(UNSUBSCRIBE_SECRET_KEY='sooper-secret'):
            real_token = unsubscribe.generate_unsubscribe_token(par)

        # First, demonstrate that our token uses a salt
        salted_token = _sha_256_signed(payload, salt='ws.email.unsubscribe')
        self.assertEqual(salted_token, real_token)

        # Then, show that the unsalted version of the same payload doesn't match
        unsalted_token = _sha_256_signed(payload, salt=None)
        self.assertNotEqual(salted_token, unsalted_token)

        # Finally, other signers which might use the same secret, but a different salt don't match
        other_salt_token = _sha_256_signed(payload, salt='some.other.module')
        self.assertNotEqual(salted_token, other_salt_token)


@freeze_time("2021-12-10 12:00:00 EST")
class UnsubscribeFromTokenTest(TestCase):
    def test_participant_since_deleted(self):
        par = factories.ParticipantFactory.create()
        token = unsubscribe.generate_unsubscribe_token(par)
        par.delete()
        with self.assertRaises(unsubscribe.InvalidToken) as cm:
            unsubscribe.unsubscribe_from_token(token)
        self.assertEqual(str(cm.exception), "Participant no longer exists")

    def test_bad_token(self):
        with self.assertRaises(unsubscribe.InvalidToken) as cm:
            unsubscribe.unsubscribe_from_token('this-is-not-a-token')
        self.assertEqual(
            str(cm.exception), "Invalid token, cannot unsubscribe automatically."
        )

    def test_real_token_wrong_secret(self):
        par = factories.ParticipantFactory.build(pk=42)
        with self.settings(UNSUBSCRIBE_SECRET_KEY='different-secret'):
            token = unsubscribe.generate_unsubscribe_token(par)

        with self.assertRaises(unsubscribe.InvalidToken) as cm:
            unsubscribe.unsubscribe_from_token(token)
        self.assertEqual(
            str(cm.exception), "Invalid token, cannot unsubscribe automatically."
        )

    def test_token_expired(self):
        par = factories.ParticipantFactory.create()
        with freeze_time("2021-09-01 12:00:00 EST"):
            token = unsubscribe.generate_unsubscribe_token(par)

        with freeze_time("2021-10-03 12:00:00 EST"):
            with self.assertRaises(unsubscribe.InvalidToken) as cm:
                unsubscribe.unsubscribe_from_token(token)
        self.assertEqual(
            str(cm.exception), "Token expired, cannot unsubscribe automatically."
        )

    def test_success(self):
        par = factories.ParticipantFactory.create(send_membership_reminder=True)
        token = unsubscribe.generate_unsubscribe_token(par)
        returned_par = unsubscribe.unsubscribe_from_token(token)
        self.assertEqual(returned_par, par)

        par.refresh_from_db()
        self.assertFalse(par.send_membership_reminder)

    def test_works_even_if_already_unsubscribed(self):
        par = factories.ParticipantFactory.create(send_membership_reminder=False)
        token = unsubscribe.generate_unsubscribe_token(par)
        returned_par = unsubscribe.unsubscribe_from_token(token)
        self.assertEqual(returned_par, par)

        par.refresh_from_db()
        self.assertFalse(par.send_membership_reminder)

    def test_empty_list_technically_handled(self):
        """It doesn't make a ton of sense, but a token to unsub from zero emails should work."""
        par = factories.ParticipantFactory.create(send_membership_reminder=True)

        # Accessing private methods to make this work, but not a big deal; it's an edge case
        signer = unsubscribe._get_signer()  # pylint:disable=protected-access
        token = signer.sign_object({'pk': par.pk, 'emails': []})

        # The method succeeds! Nothing happens, of course.
        unsubscribe.unsubscribe_from_token(token)
        par.refresh_from_db()
        self.assertTrue(par.send_membership_reminder)
