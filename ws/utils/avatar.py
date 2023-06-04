import hashlib
import urllib.parse

from ws import settings


def gravatar_url(email: str, size=40):
    email_bytes = email.encode('utf-8').lower()
    email_hash = hashlib.md5(email_bytes).hexdigest()  # noqa: S324
    options = urllib.parse.urlencode({'d': 'mm', 's': size, 'r': 'pg'})
    return f"https://www.gravatar.com/avatar/{email_hash}?{options}"


def avatar_url(participant, display_size=40):
    if participant is None or participant.gravatar_opt_out:
        return settings.PRIVACY_AVATAR_URL  # SVG, so size is meaningless
    return gravatar_url(participant.email, display_size * 2)  # 2x for Retina
