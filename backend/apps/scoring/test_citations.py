from django.test import SimpleTestCase

from apps.scoring.capability.citations import expand_citation

WINDOW = [{'id': 'a', 'text': 'The Board approved the \u201cAI Policy\u201d on 12 March 2023 \u2013 effective immediately.'}]


class FoldedQuoteTests(SimpleTestCase):
    def test_straight_quotes_and_hyphens_match_and_return_the_source_text(self):
        out = expand_citation({'source_id': 'a', 'quote': 'approved the "AI Policy" on 12 March 2023 - effective'}, WINDOW)
        self.assertEqual(out[0]['quote'], 'approved the \u201cAI Policy\u201d on 12 March 2023 \u2013 effective')

    def test_a_changed_word_still_fails(self):
        with self.assertRaises(ValueError):
            expand_citation({'source_id': 'a', 'quote': 'The Board adopted the "AI Policy" on 12 March'}, WINDOW)
