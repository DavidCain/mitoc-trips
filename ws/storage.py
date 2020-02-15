from django.contrib.staticfiles.storage import ManifestFilesMixin, StaticFilesStorage
from pipeline.storage import GZIPMixin, PipelineMixin


# TODO: Remove this when we move off the old Footable.
class ManifestStorage(PipelineMixin, GZIPMixin, ManifestFilesMixin, StaticFilesStorage):
    def post_process(self, *args, **kwargs):
        for name, hashed_name, processed in super().post_process(*args, **kwargs):
            if isinstance(processed, Exception):
                message = str(processed)
                if 'footable' in message:
                    continue  # V2 required glyphicons with a relative URL...
            yield name, hashed_name, processed
