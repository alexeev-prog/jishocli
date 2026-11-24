import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from jishocli.cli import main
from jishocli.course import LESSONS
from jishocli.storage import Store


class CourseTests(unittest.TestCase):
    def test_course_has_n5_lessons_and_sources(self):
        self.assertGreaterEqual(len(LESSONS), 8)
        self.assertTrue(all(item["links"] for item in LESSONS))

    def test_course_cli(self):
        output = io.StringIO()
        with TemporaryDirectory() as home, redirect_stdout(output):
            import os
            old = os.environ.get("HOME")
            os.environ["HOME"] = home
            try:
                main(["learn"])
                main(["learn", "01", "--done"])
            finally:
                if old is None: os.environ.pop("HOME", None)
                else: os.environ["HOME"] = old
        self.assertIn("С нуля", output.getvalue())
        self.assertIn("Урок отмечен", output.getvalue())


if __name__ == '__main__':
    unittest.main()
