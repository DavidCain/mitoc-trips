import hashlib
import urllib.parse
from typing import TYPE_CHECKING

from ws import settings

if TYPE_CHECKING:
    from ws.models import Participant


def gravatar_url(email: str, size: int = 40) -> str:
    email_bytes = email.encode('utf-8').lower()
    email_hash = hashlib.md5(email_bytes).hexdigest()  # noqa: S324
    options = urllib.parse.urlencode({'d': 'mm', 's': size, 'r': 'pg'})
    return f"https://www.gravatar.com/avatar/{email_hash}?{options}"


def avatar_url(participant: 'Participant', display_size: int = 40) -> str:
    if participant is None or participant.gravatar_opt_out:
        return settings.PRIVACY_AVATAR_URL  # SVG, so size is meaningless
    return gravatar_url(participant.email, display_size * 2)  # 2x for Retina
