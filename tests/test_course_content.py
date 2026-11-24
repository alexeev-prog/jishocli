import unittest

from jishocli.course import LESSONS


class CourseContentTests(unittest.TestCase):
    def test_every_lesson_has_learning_sections(self):
        required = {"goal", "text", "grammar", "syntax", "pronunciation", "practice", "quiz", "links"}
        for item in LESSONS:
            self.assertTrue(required.issubset(item), item["id"])
            self.assertGreaterEqual(len(item["quiz"]), 2)
            self.assertGreaterEqual(len(item["links"]), 1)

    def test_course_ids_are_ordered(self):
        self.assertEqual([item["id"] for item in LESSONS], [f"{i:02d}" for i in range(1, 25)])


if __name__ == "__main__":
    unittest.main()
