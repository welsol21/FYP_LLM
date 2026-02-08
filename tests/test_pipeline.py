import unittest

from ela_pipeline.inference.run import run_pipeline


class PipelineTests(unittest.TestCase):
    def test_pipeline_without_generator(self):
        out = run_pipeline("She should have trusted her instincts before making the decision.", model_dir=None)
        self.assertIsInstance(out, dict)
        key = next(iter(out))
        self.assertEqual(out[key]["type"], "Sentence")


if __name__ == "__main__":
    unittest.main()
