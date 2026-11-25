"""For the tests written before results were published (capability/publication.py).

Those tests are about the assessment, its reports and its screens, and read every completed run as the college's own
coordinator, straight after it completes. In the product InGage staff publish a result first, and a college downloads
a report only once its text is written and checked. `every_result_published(test)` lets such a test go on reading as
before: every completed run counts as published to the college, every report as ready, and the coordinator keeps the
technical appendix and the JSON export (staff-only now). Only those checks are replaced; sprint and institution
scoping still apply. test_publication.py tests the rule itself, on the same flow.
"""
from unittest import mock

READY = {'ready': True, 'reasons': [], 'warnings': [], 'explanations': None, 'next_steps': None}


def every_result_published(test):
    if getattr(test, 'publication_rules', False):   # a test of the rule itself (test_publication.py)
        return
    for name, replacement in (('require_visible', lambda user, execution: None),
                              ('readiness', lambda execution: dict(READY)),
                              ('is_staff', lambda user: True)):
        patcher = mock.patch(f'apps.scoring.capability.publication.{name}', replacement)
        patcher.start()
        test.addCleanup(patcher.stop)
