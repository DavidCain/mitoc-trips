from types import MappingProxyType

# An enumeration of all lists that we can provide as options for unsubscription
# This does excludes mailing lists that are known, but not intended for self-service.
# For example, the Winter School participant list is not included here.
# See; https://mitoc.mit.edu/#mailing-lists
KNOWN_MAILING_LISTS = MappingProxyType(
    {
        'General': [
            'mitoc',
            'mitoc-announce',
            'mitoc-trip-announce',
        ],
        'Activity': [
            'climber-yoga',
            'climbers',
            'climbing-wall',
            'mitoc-bcski',
            'mitoc-bike',
            'mitoc-expeditions',
            'mitoc-mountainrunning',
            'mitoc-wind',
            'mountaineering',
            'paddle',
            'surfers',
        ],
        'Regional': [
            'mitoc-alps',
            'mitoc-bayarea',
            'mitoc-rockies',
            'mitoc-seattle',
            'mitoc-socal',
        ],
        'Other': [
            'cabin-helpers',
            'conservation',
            'mitoc-gear',
            'mitoc-housing',
            'mitoc-training',
        ],
    }
)
