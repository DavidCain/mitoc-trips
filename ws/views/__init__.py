"""Views are broken up, loosely grouped by purpose."""
# I really should move away from `import *` and do imports explicitly.

from .account import *  # noqa: F403
from .applications import *  # noqa: F403
from .duplicates import *  # noqa: F403
from .itinerary import *  # noqa: F403
from .leaders import *  # noqa: F403
from .membership import *  # noqa: F403
from .participant import *  # noqa: F403
from .preferences import *  # noqa: F403
from .privacy import *  # noqa: F403
from .signup import *  # noqa: F403
from .stats import *  # noqa: F403
from .trips import *  # noqa: F403
from .winter_school import *  # noqa: F403
