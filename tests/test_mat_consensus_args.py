import unittest

from mat import parse_consensus_args


class ParseConsensusArgsTests(unittest.TestCase):
    def test_defaults_timeout_and_min_responses(self):
        opts = parse_consensus_args("hello world")
        self.assertEqual(opts.prompt, "hello world")
        self.assertEqual(opts.timeout, 30.0)
        self.assertEqual(opts.min_responses, 2)

    def test_parses_timeout_and_min_responses_flags(self):
        opts = parse_consensus_args("--timeout 12 --min-responses 3 hello world")
        self.assertEqual(opts.prompt, "hello world")
        self.assertEqual(opts.timeout, 12.0)
        self.assertEqual(opts.min_responses, 3)


if __name__ == "__main__":
    unittest.main()
