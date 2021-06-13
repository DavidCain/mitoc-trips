def label_is_both(label):
    return label in {'contenttypes'}


def label_is_auth(label):
    """Return if the label belongs exclusively to the auth_db."""
    return label in {'auth', 'account', 'admin', 'sessions'}


def is_auth(obj, **hints):
    if hints.get('target_db') == 'auth_db':
        return True
    return label_is_auth(obj._meta.app_label)  # pylint: disable=protected-access


class AuthRouter:
    """
    A router to control all database operations on models in the
    auth application.
    """

    @staticmethod
    def db_for_read(model, **hints):
        """
        Attempts to read auth models go to auth_db.
        """
        if is_auth(model, **hints):
            return 'auth_db'
        return None

    @staticmethod
    def db_for_write(model, **hints):
        """
        Attempts to write auth models go to auth_db.
        """
        if is_auth(model, **hints):
            return 'auth_db'
        return None

    @staticmethod
    def allow_relation(obj1, obj2, **hints):
        """
        Allow relations if a model in the auth app is involved.
        """
        if is_auth(obj1, **hints) or is_auth(obj2, **hints):
            return True
        return None

    @staticmethod
    def allow_migrate(db, app_label, model_name=None, **hints):
        """
        Make sure the auth app only appears in the 'auth_db' database.
        """
        if 'target_db' in hints:
            return db == hints['target_db']

        if label_is_both(app_label):
            return True

        if label_is_auth(app_label):
            return db == 'auth_db'
        if app_label == 'ws':
            return db == 'default'
        return None
