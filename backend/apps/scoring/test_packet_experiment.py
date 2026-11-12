from django.test import SimpleTestCase
from .capability.packet_experiment import requirement_packets
from .capability.passages import Passage


class RequirementPacketTests(SimpleTestCase):
    def trace(self):
        source={'id':'p','document_id':'d','page_number':1,'text':'# Policy\nResource review compares capacity and demand.\nThe review led to a funded upgrade.'}
        cut=source['text'].index('The review')
        ps=[Passage(source,9,cut,'prose',(0,9),source['text'][9:cut],12),
            Passage(source,cut,len(source['text']),'prose',(0,9),source['text'][cut:],10)]
        requirements=[{'condition_id':cid,'anchor':'','assertion':'Resource review capacity demand upgrade',
            'evidence_query':'funded upgrade','lexical':[0,1],'semantic':[0,1],
            'lexical_scores':[3.,2.],'similarity':[.8,.7]} for cid in ['a','b']]
        return {'passages':ps,'requirements':requirements,'expansion_exclusions':{}}

    def test_each_assertion_has_owned_budget_and_exact_independent_source_spans(self):
        trace=self.trace();result=requirement_packets(trace,budget=200)
        self.assertLessEqual(result['used_chars'],200)
        self.assertEqual([p['allowance'] for p in result['packets']],[100,100])
        for packet in result['packets']:
            self.assertLessEqual(packet['used_chars'],packet['allowance'])
            for s in packet['sources']:
                self.assertEqual(s['text'],trace['passages'][0].source['text'][s['text_offset']:s['text_offset']+len(s['text'])])
        self.assertLessEqual(result['unique_chars'],result['used_chars'])

    def test_adjacent_expansion_retains_source_offsets_and_charges_for_context(self):
        trace=self.trace();result=requirement_packets(trace,budget=200,expand=True)
        self.assertTrue(result['adjacent_expansion'])
        self.assertEqual(result['packets'][0]['used_chars'],len(trace['passages'][0].source['text']))
        self.assertEqual(result['packets'][0]['sources'][0]['text_offset'],0)

    def test_short_headings_do_not_win_only_because_they_are_short(self):
        trace=self.trace();source={'id':'header','text':'Review'}
        trace['passages'].append(Passage(source,0,6,'heading',None,'Review',1))
        for r in trace['requirements']:
            r['lexical'].append(2);r['semantic'].append(2);r['lexical_scores'].append(.01);r['similarity'].append(.01)
        result=requirement_packets(trace,budget=200)
        self.assertTrue(all(p['selected_candidates'][0]==0 for p in result['packets']))
