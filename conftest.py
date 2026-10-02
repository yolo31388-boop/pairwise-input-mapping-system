"""Pytest bootstrap.

The placeholder test class in tests/test_input_mapping.py does not inherit
unittest.TestCase, so its ``self.assertIsNotNone`` calls raise AttributeError.
Supply that method (a plain function on the class is sufficient: when the
asserted value is not None, unittest's implementation does not touch self).
"""

import unittest


def pytest_pycollect_makeitem(collector, name, obj):
    if isinstance(obj, type) and name.startswith("Test"):
        if not hasattr(obj, "assertIsNotNone"):
            obj.assertIsNotNone = unittest.TestCase.assertIsNotNone
    return None
