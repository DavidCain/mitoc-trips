class DefaultOnlyRouter:
    @staticmethod
    def allow_migrate(db, app_label, model_name=None, **hints):
        """
        Make sure the auth app only appears in the 'auth_db' database.
        """
        if 'target_db' in hints:
            return db == hints['target_db']

        if app_label == 'ws':
            return db == 'default'

        # Importantly, we don't actually run migrations on our test `geardb`
        return None
