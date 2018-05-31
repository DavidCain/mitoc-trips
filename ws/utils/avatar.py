import hashlib
import urllib.parse

from ws import settings


def gravatar_url(email, size=40):
    if isinstance(email, str):  # Bytestrings okay, unicode must be encoded
        email = email.encode('utf-8')
    email_hash = hashlib.md5(email.lower()).hexdigest()
    options = urllib.parse.urlencode({'d': 'mm', 's': size, 'r': 'pg'})
    return f"https://www.gravatar.com/avatar/{email_hash}?{options}"


def avatar_url(participant, display_size=40):
    if participant is None or participant.gravatar_opt_out:
        return settings.PRIVACY_AVATAR_URL  # SVG, so size is meaningless
    return gravatar_url(participant.email, display_size * 2)  # 2x for Retina
