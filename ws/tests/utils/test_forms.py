import unittest

from ws.utils.forms import all_choices


class FormUtilTests(unittest.TestCase):
    def test_normal_case(self):
        choices = [
            ("none", "not at all"),
            ("some", "some exposure"),
            ("comfortable", "comfortable"),
            ("very comfortable", "very comfortable"),
        ]
        self.assertEqual(
            list(all_choices(choices)),
            ["none", "some", "comfortable", "very comfortable"],
        )

    def test_mixed_named_groups(self):
        """It works mixing named groups & non-groups."""
        choices = [
            (
                "Undergraduate student",
                [("MU", "MIT undergrad"), ("NU", "Non-MIT undergrad")],
            ),
            (
                "Graduate student",
                [("MG", "MIT grad student"), ("NG", "Non-MIT grad student")],
            ),
            (
                "MIT",
                [
                    ("MA", "MIT affiliate (staff or faculty)"),
                    ("ML", "MIT alum (former student)"),
                ],
            ),
            ("NA", "Non-affiliate"),
        ]
        self.assertEqual(
            list(all_choices(choices)), ["MU", "NU", "MG", "NG", "MA", "ML", "NA"]
        )

    def test_nested_groups(self):
        """Nested named groups are handled properly."""
        choices = [
            (
                "MIT",
                [
                    ("Student", [("MU", "MIT undergrad"), ("MG", "MIT grad student")]),
                    (
                        "Non-student",
                        [
                            ("MA", "MIT affiliate (staff or faculty)"),
                            ("ML", "MIT alum (former student)"),
                        ],
                    ),
                ],
            ),
            (
                "Non-MIT",
                [
                    ("NA", "Non-affiliate"),
                    ("NG", "Non-MIT grad student"),
                    ("NU", "Non-MIT undergrad"),
                ],
            ),
        ]
        self.assertEqual(
            list(all_choices(choices)), ["MU", "MG", "MA", "ML", "NA", "NG", "NU"]
        )
