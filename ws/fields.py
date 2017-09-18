from django.db import models


class OptionalOneToOneField(models.OneToOneField):
    """ One-to-one relationships in schema can (and often will be) null. """
    def __init__(self, *args, **kwargs):
        null = kwargs.pop('null', True)
        blank = kwargs.pop('blank', True)
        return super().__init__(*args, null=null, blank=blank, **kwargs)
