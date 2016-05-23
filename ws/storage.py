from pipeline.storage import PipelineCachedStorage


class CachedStorage(PipelineCachedStorage):
    def post_process(self, paths, dry_run=False, **options):
        super_class = super(CachedStorage, self)
        for name, hashed_name, processed in super_class.post_process(paths.copy(), dry_run, **options):
            if hashed_name != name:
                paths[hashed_name] = (self, hashed_name)
            if isinstance(processed, Exception):
                if 'chrome:/' in processed.message:
                    continue  # Django bug parsing  `url: 'chrome://...'`
                if 'footable' in processed.message:
                    continue  # V2 required glyphicons with a relative URL...
            yield name, hashed_name, processed
