from copy import deepcopy
from django.test import SimpleTestCase
from .capability.probe_cases import request_from_bundle
from .capability.engine import release
from .capability.storage import digest
from .capability.evidence_cases import VERSION


class NamedProbeBundleTests(SimpleTestCase):
    def fixture(self):
        rubric=release();condition=rubric['indicators'][0]['conditions'][0]
        sources=[{'id':'cover','document_id':'d','page_number':1,'text':'Accreditation council'},
            {'id':'directory','document_id':'d','page_number':2,'text':'The upload directory lists the requested teacher training records.'}]
        controls=[{'id':bid,'citations':[{'document_id':'d','page':source['page_number'],'quote':source['text']}],
            'expected_on_this_packet':'unknown','reason':'This isolated control does not establish the assertion.'}
            for bid,source in zip(('cover_title','upload_row'),sources)]
        return {'rubric':rubric,'sources':sources},{'version':VERSION,'source_corpus_hash':digest(sources),
            'rubric_hash':digest(rubric),'cases':[{'condition_id':condition['id'],'assertion':condition['text'],
            'positive_bundles':[],'insufficient_controls':controls}]},condition['id']

    def build(self,replay,pack,cid,bid='upload_row'):
        return request_from_bundle(replay,pack,cid,bid,ledger={'claims':[],'issues':[]},scope=None,
            population='Learners',reference_period='Source-specific')

    def test_bundle_order_cannot_change_which_control_reaches_the_model(self):
        replay,pack,cid=self.fixture();first=self.build(replay,pack,cid)
        pack['cases'][0]['insufficient_controls'].reverse()
        second=self.build(replay,pack,cid)
        self.assertEqual(first['payload'],second['payload'])
        self.assertEqual(first['payload']['sources'][0]['page_number'],2)
        self.assertEqual(first['evidence_bundle_id'],'upload_row')
        self.assertNotIn('expected_interpretation',first['payload'])

    def test_unknown_id_and_ambiguous_source_span_fail_before_a_request_can_be_built(self):
        replay,pack,cid=self.fixture()
        with self.assertRaises(ValueError):self.build(replay,pack,cid,'missing')
        replay=deepcopy(replay);replay['sources'][1]['text']+=' '+replay['sources'][1]['text']
        pack['source_corpus_hash']=digest(replay['sources'])
        with self.assertRaisesMessage(ValueError,'unambiguous'):self.build(replay,pack,cid)
