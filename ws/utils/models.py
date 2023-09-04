from collections.abc import Iterator
from typing import TYPE_CHECKING, Optional

from ws import enums

if TYPE_CHECKING:
    from ws.models import Participant


def problems_with_profile(
    participant: Optional['Participant'],
) -> Iterator[enums.ProfileProblem]:
    if participant is None:
        yield enums.ProfileProblem.NO_INFO
        return

    yield from participant.problems_with_profile
