"""The same-area band (same-area-1, CAPABILITY_MAP_SAME_AREA). No model calls."""
from django.test import SimpleTestCase, override_settings

from apps.scoring.capability.evaluation import map_argument
from apps.scoring.capability.semantic_retrieval import configured_policy

from . import packet, spec
from .test_packet import FILLER, indicator, keyword_fill, page, tag


def siblings(code):
    from apps.scoring.capability.engine import release
    return [i['code'] for i in release()['indicators']
            if packet.area_of(i['code']) == packet.area_of(code) and i['code'] != code]


class SameAreaBandTests(SimpleTestCase):
    def setUp(self):
        self.ind = indicator('AIQIF-C9.2')
        self.sibling = siblings(self.ind['code'])[0]
        self.req = [c['id'] for c in self.ind['conditions']]
        self.own = page('own', 'doc-a', 1, 'Own page. ' + FILLER * 3)
        self.near = page('near', 'doc-b', 4, 'Sibling page. ' + FILLER * 3)
        self.far = page('far', 'doc-c', 2, 'Other area page. ' + FILLER * 3)
        self.vague = page('vague', 'doc-d', 7, 'Sibling topical page. ' + FILLER * 3)
        self.plain = page('plain', 'doc-e', 1, 'Plain page. ' + FILLER * 3)
        self.sources = [self.plain, self.vague, self.far, self.near, self.own]
        self.frozen = {'pages': {
            spec.text_hash(self.own['text']): {'page_type': 'other', 'tags': [tag(self.ind['code'], 'direct', self.req[:1])]},
            spec.text_hash(self.near['text']): {'page_type': 'other', 'tags': [tag(self.sibling, 'supporting')]},
            spec.text_hash(self.far['text']): {'page_type': 'other', 'tags': [tag('AIQIF-C1.1', 'direct')]},
            spec.text_hash(self.vague['text']): {'page_type': 'other', 'tags': [tag(self.sibling, 'topical')]}}}

    def steps(self, trace):
        return {w['id']: w['reasons'][0]['step'] for w in trace['windows']}

    def test_off_by_default_a_sibling_tag_is_only_keyword_fill(self):
        _, trace = packet.build(self.ind, self.sources, self.frozen, cap=60000, keyword_fill=keyword_fill)
        self.assertEqual(self.steps(trace)['near'], 'keyword_fill')
        self.assertNotIn('same_area', trace)

    def test_on_the_areas_strong_tags_follow_the_indicators_own(self):
        context, trace = packet.build(self.ind, self.sources, self.frozen, cap=60000, keyword_fill=keyword_fill,
                                      same_area=True)
        self.assertEqual([w['id'] for w in context][:2], ['own', 'near'])
        steps = self.steps(trace)
        self.assertEqual((steps['own'], steps['near']), ('direct', 'same_area_supporting'))
        self.assertNotIn(steps['far'], ('same_area_direct', 'same_area_supporting'))     # another area
        self.assertNotIn(steps['vague'], ('same_area_direct', 'same_area_supporting'))   # topical for the sibling
        self.assertEqual(trace['same_area']['version'], packet.SAME_AREA_VERSION)
        self.assertEqual(trace['same_area']['chosen'], 1)
        near = next(w for w in trace['windows'] if w['id'] == 'near')
        self.assertEqual(near['reasons'][0]['tag_indicator'], self.sibling)
        self.assertNotIn('tag_indicator', context[1])    # the judge sees plain windows

    def test_the_band_stays_inside_the_tagged_share(self):
        many = [page(f's{n}', f'doc-s{n}', n, f'Sibling {n}. ' + FILLER * 20) for n in range(40)]
        frozen = {'pages': {**self.frozen['pages'], **{
            spec.text_hash(p['text']): {'page_type': 'other', 'tags': [tag(self.sibling, 'supporting')]} for p in many}}}
        _, trace = packet.build(self.ind, self.sources + many, frozen, cap=60000, keyword_fill=keyword_fill,
                                same_area=True)
        own = next(w['chars'] for w in trace['windows'] if w['id'] == 'own')
        band = trace['same_area']['chars']
        self.assertLessEqual(band, (40000 - own) * packet.SAME_AREA_SHARE[0] // packet.SAME_AREA_SHARE[1])
        self.assertLessEqual(trace['tagged_chars'], 40000)
        self.assertGreater(trace['left_out_for_space'].get('same_area_supporting', 0), 0)

    def test_the_same_inputs_give_the_same_packet(self):
        first = packet.build(self.ind, self.sources, self.frozen, cap=60000, keyword_fill=keyword_fill, same_area=True)
        second = packet.build(self.ind, list(reversed(self.sources)), self.frozen, cap=60000,
                              keyword_fill=keyword_fill, same_area=True)
        self.assertEqual([w['id'] for w in first[0]][:2], [w['id'] for w in second[0]][:2])


class SameAreaPolicyTests(SimpleTestCase):
    settings = dict(CAPABILITY_RETRIEVAL_MODE='map', CAPABILITY_MAX_INPUT_TOKEN_BOUND=400000,
                    CAPABILITY_EVIDENCE_LANE=False, CAPABILITY_FOLLOW_UP_SEARCH=False,
                    CAPABILITY_PROMPT_TOKEN_CEILING=None)

    def test_off_by_default(self):
        with override_settings(**self.settings):
            self.assertNotIn('same_area', configured_policy())

    def test_on_it_is_frozen_and_reaches_the_packet(self):
        with override_settings(**self.settings, CAPABILITY_MAP_SAME_AREA=True):
            policy = configured_policy()
        self.assertEqual(policy['same_area'], packet.SAME_AREA_VERSION)
        self.assertEqual(policy['allocation'], packet.ALLOCATION)
        self.assertTrue(map_argument(policy, {'pages': {}})['same_area'])

    def test_a_run_frozen_with_another_band_version_is_refused(self):
        with override_settings(**self.settings, CAPABILITY_MAP_SAME_AREA=True):
            policy = configured_policy()
        with self.assertRaises(ValueError):
            map_argument({**policy, 'same_area': 'same-area-0'}, {'pages': {}})
