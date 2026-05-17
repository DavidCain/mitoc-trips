import hashlib
import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ws.models import Participant


def gravatar_url(email: str, size: int = 40) -> str:
    email_bytes = email.encode("utf-8").lower()
    email_hash = hashlib.md5(email_bytes).hexdigest()  # noqa: S324
    options = urllib.parse.urlencode({"d": "mm", "s": size, "r": "pg"})
    return f"https://www.gravatar.com/avatar/{email_hash}?{options}"


def avatar_url(participant: "Participant", display_size: int = 40) -> str:
    if participant is None or participant.gravatar_opt_out:
        # URL to an avatar image that is self-hosted
        # (Users who opt out of Gravatar would prefer to not have requests made to
        #  Gravatar to fetch the "mystery man" image)
        return "https://s3.amazonaws.com/mitoc-trips/privacy/avatar.svg"
    return gravatar_url(participant.email, display_size * 2)  # 2x for Retina
