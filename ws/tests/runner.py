import os
import os.path
from pathlib import Path

from django.test.runner import DiscoverRunner


class SetupGearDbTestRunner(DiscoverRunner):
    """
    Set up a minimal set of gear database tables using raw SQL.

    The actual geardb project is an entirely separate Django application,
    where tables are managed with models there.

    We could use unmanaged models (`class Meta: unmanaged = True`) to manage
    these tables, but that would basically call for duplicating code from the
    geardb project. This is a minimal, efficient solution to getting the same
    schema in raw SQL, which is the query language we use to access them.

    This runner will be obsolete when we move the `utils.geardb` functions to
    instead call an API managed by the gear database itself.
    """

    @property
    def sql_commands(self):
        schema = Path(os.path.dirname(__file__), 'basic_geardb_schema.sql')
        with schema.open() as handle:
            sql = handle.read().strip()
            return (c.strip() for c in sql.split(';') if c.strip())

    def setup_databases(self, *args, **kwargs):
        config = super().setup_databases(*args, **kwargs)

        # `geardb` should *always* be specified at present
        # (the other two main databases list it as a dependency)
        geardb = next(wrapper for (wrapper, name, _) in config if name == 'geardb')

        with geardb.connection.cursor() as cursor:
            for cmd in self.sql_commands:
                cursor.execute(cmd)

        return config
