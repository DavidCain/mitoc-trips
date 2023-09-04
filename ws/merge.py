"""
Allow merging two duplicate participants.

Some users forget their old account information, and either are not aware of how they
can reset their passwords, or just don't bother.

Because many participants have information split across accounts, we should
occasionally merge these accounts into one. The end result is that they get an
account where they can log in with either email address, and get access to a
complete history.
"""
from collections.abc import Iterable
from typing import cast

from django.db import connections, transaction
from django.db.backends.utils import CursorWrapper

from ws import models

# An enumeration of columns that we explicitly intend to migrate in `ws`, grouped by table
# If any table has a column with a foreign key to ws_participant that is not in here, we will error
# Unless explicitly handled, each will be automatically migrated
EXPECTED_PARTICIPANT_TABLES: dict[str, tuple[str, ...]] = {
    'ws_trip': ('creator_id', 'wimp_id', 'last_updated_by_id'),
    'ws_leaderrating': ('participant_id', 'creator_id'),
    'ws_feedback': ('participant_id', 'leader_id'),
    'ws_lotteryinfo': ('participant_id', 'paired_with_id'),
    'ws_lotteryadjustment': ('creator_id', 'participant_id'),
    'ws_lotteryseparation': ('creator_id', 'initiator_id', 'recipient_id'),
    'ws_climbingleaderapplication': ('participant_id',),
    'ws_hikingleaderapplication': ('participant_id',),
    'ws_winterschoolleaderapplication': ('participant_id',),
    'ws_leaderrecommendation': ('creator_id', 'participant_id'),
    'ws_lectureattendance': ('participant_id', 'creator_id'),
    'ws_winterschoolsettings': ('last_updated_by_id',),
    'ws_discount_administrators': ('participant_id',),
    'ws_distinctaccounts': ('left_id', 'right_id'),
    # Each of these tables should only have one row for the given person.
    # (For example, it's possible that two participants representing the same human are on the same trip.
    # In practice, though, this should never actually be happening. Uniqueness constraints will protect us.
    'ws_tripinfo_drivers': ('participant_id',),
    'ws_participant_discounts': ('participant_id',),
    'ws_trip_leaders': ('participant_id',),
    'ws_leadersignup': ('participant_id',),
    'ws_signup': ('participant_id',),
    'ws_passwordquality': ('participant_id',),
    'ws_membershipreminder': ('participant_id',),
}

# An enumeration of user FK columns that we explicitly intend to migrate
# Each one must be *manually handled!*
EXPECTED_USER_TABLES: dict[str, tuple[str, ...]] = {
    'auth_user_groups': ('user_id',),
    'auth_user_user_permissions': ('user_id',),
    'account_emailaddress': ('user_id',),
    'django_admin_log': ('user_id',),
    'socialaccount_socialaccount': ('user_id',),
    'ws_participant': ('user_id',),
}


def simple_fk_update(
    cursor: CursorWrapper,
    table: str,
    col: str,
    old_pk: int,
    new_pk: int,
) -> None:
    """For tables that don't have unique constraints, copy over FKs.

    Note that this naive approach doesn't handle the case where you might
    end up with duplicate data in the same table. It's up to the caller
    to sort that out.
    """
    cursor.execute(
        f"""
        update {table}
           set {col} = %(new_pk)s
         where {col} = %(old_pk)s
        """,  # noqa: S608
        {'new_pk': new_pk, 'old_pk': old_pk},
    )


def _fk_tables(
    cursor: CursorWrapper, src_table: str, col: str
) -> Iterable[tuple[str, str, str]]:
    """Identify all other tables that point to the source table's column.

    This is useful for ensuring that we migrate over all FKs.
    """
    cursor.execute(
        """
        select (select r.relname
                  from pg_class r
                 where r.oid = c.conrelid) as table,
               (select attname
                  from pg_attribute
                 where attrelid = c.conrelid and ARRAY[attnum] <@ c.conkey) as col,
               (select r.relname
                  from pg_class r
                 where r.oid = c.confrelid) as ftable
          from pg_constraint c
         where c.confrelid = (select oid from pg_class where relname = %s) and
               c.confkey @> (select array_agg(attnum)
                               from pg_attribute
                              where attname = %s and
                                    attrelid = c.confrelid)
    """,
        (src_table, col),
    )
    return cast(Iterable[tuple[str, str, str]], cursor.fetchall())


def check_fk_tables(
    cursor: CursorWrapper,
    src_table: str,
    column: str,
    expected: dict[str, tuple[str, ...]],
) -> None:
    """Check that the foreign keys are what we expect them to be.

    Useful as a canary that things may go wrong if we've since added
    more foreign keys.
    """
    non_handled = []
    for table, col, _ftable in _fk_tables(cursor, src_table, column):
        if col not in expected.get(table, ()):
            non_handled.append((table, col))
    if non_handled:
        missing = ','.join(f"{table}.{col}" for table, col in non_handled)
        raise ValueError(f"Database has more FKs. Not handled: {missing}")


def _update_lotteryinfo(cursor, old_pk, new_pk):
    """Ensure one current lotteryinfo object per participant.

    Since each participant can only have one lotteryinfo object:
    - copy over the old if no new object present
    - delete the old if a new object present
    """
    cursor.execute(
        """
        select exists(
          select
            from ws_lotteryinfo
           where participant_id = %(new_pk)s
        )
        """,
        {'new_pk': new_pk},
    )
    if cursor.fetchone()[0]:
        sql = "delete from ws_lotteryinfo where participant_id = %(old_pk)s"
    else:
        sql = """
            update ws_lotteryinfo
               set participant_id = %(new_pk)s
             where participant_id = %(old_pk)s
            """
    cursor.execute(sql, {'old_pk': old_pk, 'new_pk': new_pk})


def _migrate_user(old_pk: int, new_pk: int) -> None:
    """Copy over any email addresses and groups from the old user."""
    cursor = connections['default'].cursor()

    check_fk_tables(cursor, 'auth_user', 'id', EXPECTED_USER_TABLES)

    cursor.execute("select count(*) from auth_user_user_permissions")
    if cursor.fetchone()[0]:
        raise ValueError("Permissions exist, but this script doesn't handle that")

    # There should only be one primary, taken from the new account
    cursor.execute(
        """
        update account_emailaddress
           set "primary" = false
         where user_id = %(old_pk)s
        """,
        {'old_pk': old_pk},
    )
    for table in ['account_emailaddress', 'django_admin_log']:
        simple_fk_update(cursor, table, 'user_id', old_pk, new_pk)

    # Copy over old groups the user no longer has (duplicates are constrained)
    cursor.execute(
        """
        with existing as (
          select group_id
            from auth_user_groups
           where user_id = %(old_pk)s
        )
        update auth_user_groups
           set user_id = %(new_pk)s
         where user_id = %(old_pk)s and
              group_id not in (select group_id from existing)
        """,
        {'old_pk': old_pk, 'new_pk': new_pk},
    )

    cursor.execute(
        "delete from auth_user_groups where user_id = %(old_pk)s", {'old_pk': old_pk}
    )
    cursor.execute("delete from auth_user where id = %(old_pk)s", {'old_pk': old_pk})
    # Simply delete any Social login accounts
    # (For Gmail it's pretty trivial to re-authorize)
    cursor.execute(
        "delete from socialaccount_socialaccount where user_id = %(old_pk)s",
        {'old_pk': old_pk},
    )


def _migrate_participant(old_pk, new_pk):
    """Copy over references to the old participant to belong to the new."""
    cursor = connections['default'].cursor()

    check_fk_tables(cursor, 'ws_participant', 'id', EXPECTED_PARTICIPANT_TABLES)

    _update_lotteryinfo(cursor, old_pk, new_pk)

    simple_updates = EXPECTED_PARTICIPANT_TABLES.copy()

    # When we merge participants, we'll be merging user records.
    # Accordingly, we're keeping the password from the "new" participant's user.
    # Just delete any record of password quality on the old participant.
    simple_updates.pop('ws_passwordquality')
    models.PasswordQuality.objects.filter(participant_id=old_pk).delete()

    # We want to be very sure that we don't notify the same human twice in one year.
    # (We also can have only one row per participant)
    # If two reminders are found, just keep the most recent one.
    reminders = models.MembershipReminder.objects.filter(
        participant_id__in=[old_pk, new_pk]
    )
    if len(reminders) == 2:
        reminders.order_by('reminder_sent_at').first().delete()

    for table, cols in simple_updates.items():
        for col in cols:
            simple_fk_update(cursor, table, col, old_pk, new_pk)

    cursor.execute(
        "delete from ws_participant where id = %(old_pk)s", {'old_pk': old_pk}
    )


def merge_participants(old, new):
    with transaction.atomic():  # Roll back if FK migration fails
        _migrate_user(old.user_id, new.user_id)
        _migrate_participant(old.pk, new.pk)
