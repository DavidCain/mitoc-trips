"""
Allow merging two duplicate participants.

Some users forget their old account information, and either are not aware of how they
can reset their passwords, or just don't bother.

Because many participants have information split across accounts, we should
occasionally merge these accounts into one. The end result is that they get an
account where they can log in with either email address, and get access to a
complete history.
"""

from django.db import connections, transaction


def simple_fk_update(cursor, table, col, old_pk, new_pk):
    """ For tables that don't have unique constraints, copy over FKs.

    Note that this naive approach doesn't handle the case where you might
    end up with duplicate data in the same table. It's up to the caller
    to sort that out.
    """
    cursor.execute(
        """
        update {table}
           set {col} = {new_pk}
         where {col} = {old_pk}
        """.format(table=table, col=col, new_pk=new_pk, old_pk=old_pk)
    )


def fk_tables(cursor, src_table, col):
    """ Identify all other tables that point to the source table's column.

    This is useful for ensuring that we migrate over all FKs.
    """
    cursor.execute("""
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
    """, (src_table, col))
    return cursor.fetchall()


def check_fk_tables(cursor, src_table, col, expected):
    """ Check that the foreign keys are what we expect them to be.

    Useful as a canary that things may go wrong if we've since added
    more foreign keys.
    """
    non_handled = []
    for table, col, ftable in fk_tables(cursor, src_table, col):
        if col not in expected.get(table, {}):
            non_handled.append((table, col))
    if non_handled:
        print("The following foreign keys are not properly handled:")
        for table, col in non_handled:
            print((col + '\t' + table))
        raise ValueError("Database has more FKs than we're handling")


def update_lotteryinfo(cursor, old_pk, new_pk):
    """ Ensure one current lotteryinfo object per participant.

    Since each participant can only have one lotteryinfo object:
    - copy over the old if no new object present
    - delete the old if a new object present
    """
    cursor.execute(
        """
        select exists(
          select
            from ws_lotteryinfo
           where participant_id = {new_pk}
        )
        """.format(new_pk=new_pk)
    )
    if cursor.fetchone()[0]:
        sql = "delete from ws_lotteryinfo where participant_id = {}".format(old_pk)
    else:
        sql = """
            update ws_lotteryinfo
               set participant_id = {new_pk}
             where participant_id = {old_pk}
            """.format(new_pk=new_pk, old_pk=old_pk)
    cursor.execute(sql)


def migrate_user(old_pk, new_pk):
    """ Copy over any email addresses and groups from the old user. """
    cursor = connections['auth_db'].cursor()

    expected_tables = [
        'auth_user_user_permissions',
        'account_emailaddress',
        'django_admin_log',
        'auth_user_groups',
    ]
    expected = {key: 'user_id' for key in expected_tables}
    check_fk_tables(cursor, 'auth_user', 'id', expected)

    cursor.execute("select count(*) from auth_user_user_permissions")
    if cursor.fetchone()[0]:
        raise ValueError("Permissions exist, but this script doesn't handle that")

    # There should only be one primary, taken from the new account
    cursor.execute(
        """
        update account_emailaddress
           set "primary" = false
         where user_id = {old_pk}
        """.format(old_pk=old_pk)
    )
    for table in ['account_emailaddress', 'django_admin_log']:
        simple_fk_update(cursor, table, 'user_id', old_pk, new_pk)

    # Copy over old groups the user no longer has (duplicates are constrained)
    cursor.execute(
        """
        with existing as (
          select group_id
            from auth_user_groups
           where user_id = {old_pk}
        )
        update auth_user_groups
           set user_id = {new_pk}
         where user_id = {old_pk} and
              group_id not in (select group_id from existing)
        """.format(new_pk=new_pk, old_pk=old_pk)
    )

    cursor.execute("delete from auth_user_groups where user_id = {}".format(old_pk))
    cursor.execute("delete from auth_user where id = {}".format(old_pk))


def migrate_participant(old_pk, new_pk):
    """ Copy over references to the old participant to belong to the new. """
    cursor = connections['default'].cursor()

    expected = {
        'ws_trip': {'creator_id'},
        'ws_leaderrecommendation': {'creator_id'},
        'ws_leaderrating': {'participant_id', 'creator_id'},
        'ws_feedback': {'participant_id', 'leader_id'},
        'ws_lotteryinfo': {'participant_id', 'paired_with_id'},

        'ws_climbingleaderapplication': {'participant_id'},
        'ws_hikingleaderapplication': {'participant_id'},
        'ws_winterschoolleaderapplication': {'participant_id'},
        'ws_leaderrecommendation': {'creator_id', 'participant_id'},

        'ws_lectureattendance': {'participant_id', 'creator_id'},

        'ws_winterschoolsettings': {'last_updated_by_id'},
        'ws_discount_administrators': {'participant_id'},


        # All these should only have one participant each
        # (In practice, we should rarely see the old & the new on the same object)
        'ws_tripinfo_drivers': {'participant_id'},
        'ws_participant_discounts': {'participant_id'},
        'ws_trip_leaders': {'participant_id'},
        'ws_leadersignup': {'participant_id'},
        'ws_signup': {'participant_id'},
    }
    check_fk_tables(cursor, 'ws_participant', 'id', expected)

    update_lotteryinfo(cursor, old_pk, new_pk)

    for table, cols in expected.items():
        for col in cols:
            simple_fk_update(cursor, table, col, old_pk, new_pk)

    cursor.execute("delete from ws_participant where id = {}".format(old_pk))


def merge_people(old, new):
    with transaction.atomic():  # Rollback if FK migration fails
        migrate_user(old.user_id, new.user_id)
        migrate_participant(old.pk, new.pk)
