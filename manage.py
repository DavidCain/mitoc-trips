#!/usr/bin/env python3
import os
import sys
import warnings

# Ignore warnings that Django-Angular's Bootstrap 3 classes are going away
# 1. We're moving off of AngularJS to VueJS
# 2. Once that's done, we're going to migrate to Bootstrap 4 anyway
warnings.filterwarnings(
    action="ignore",
    category=PendingDeprecationWarning,
    module="djng.styling.bootstrap3",
)

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ws.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
