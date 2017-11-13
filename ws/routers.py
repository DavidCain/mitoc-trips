def label_is_both(label):
    return label in {'contenttypes'}


def label_is_auth(label):
    """ Return if the label belongs exclusively to the auth_db. """
    return label in {'auth', 'account', 'admin', 'sessions'}


def is_auth(obj):
    return label_is_auth(obj._meta.app_label)


class AuthRouter:
    """
    A router to control all database operations on models in the
    auth application.
    """
    def db_for_read(self, model, **hints):
        """
        Attempts to read auth models go to auth_db.
        """
        if is_auth(model):
            return 'auth_db'
        return None

    def db_for_write(self, model, **hints):
        """
        Attempts to write auth models go to auth_db.
        """
        if is_auth(model):
            return 'auth_db'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations if a model in the auth app is involved.
        """
        if is_auth(obj1) or is_auth(obj2):
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Make sure the auth app only appears in the 'auth_db' database.
        """
        if label_is_both(app_label):
            return True

        if label_is_auth(app_label):
            return db == 'auth_db'
        elif app_label == 'ws':
            return db == 'default'
        return None
