from unittest import TestCase, mock

from pipeline.storage import PipelineMixin

from ws import storage


class ManifestStorageTestCase(TestCase):
    def test_handles_problematic_footable_ref(self):
        custom_storage = storage.ManifestStorage()

        # Use two (real) paths - we'll mock one to throw an error is usually does.
        # The other path will be mocked to just gzip & fingerprint properly
        bootstrap = 'footable/demos/css/bootstrap.css'
        flag = 'bc-css-flags/lib/region-flags/svg/HN.svg'

        paths = {
            bootstrap: (custom_storage, bootstrap),
            flag: (custom_storage, flag),
        }

        def error_processing_bootstrap_path(paths, dry_run=False, **options):
            """ Simulate an error processing a footable bootstrap file (missing path) """
            for path in paths:
                if path == bootstrap:
                    processed_error = ValueError(
                        "The file 'footable/demos/img/glyphicons-halflings.png' could not be found with {storage!r}."
                    )
                    yield (path, None, processed_error)
                else:
                    assert path == 'bc-css-flags/lib/region-flags/svg/HN.svg'
                    hashed = 'bc-css-flags/lib/region-flags/svg/HN.35c4ba4b1c78.svg'
                    yield (path, hashed, True)

        # This mock is not necessary if running the test after `collectstatic`
        # (since we can actually run the real pipeline Gzipper)
        with mock.patch.object(PipelineMixin, 'post_process') as post_process:
            post_process.side_effect = error_processing_bootstrap_path
            results = list(custom_storage.post_process(paths, dry_run=False))

        expected_output = (
            'bc-css-flags/lib/region-flags/svg/HN.svg',
            'bc-css-flags/lib/region-flags/svg/HN.35c4ba4b1c78.svg',
            True,
        )

        # Notably, we just omit the footable entry from the gzipped results!
        # (Not a problem, since we forked its CSS anyway)
        self.assertEqual(results, [expected_output])
