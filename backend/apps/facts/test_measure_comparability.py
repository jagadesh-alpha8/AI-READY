from types import SimpleNamespace
from django.test import SimpleTestCase
from .verification.scope import read_scope, comparable
from .verification.conflicts import disagreements
from .verification.measures import count_basis


class MeasureComparabilityTests(SimpleTestCase):
    def fact(self, pk, label, value):
        return SimpleNamespace(pk=pk, field_key='shared_normalized_count', field_name=label, value=value,
            data_type='number', source_snippet='Students appeared and passed; national and international agreements recorded in 2024-25.',
            scope={}, retired_at=None, status='confirmed', source_document=None, document=None)

    def test_different_exam_measures_are_not_conflicting_but_same_measure_still_is(self):
        a=self.fact('a','Final year students passed after verification',120)
        b=self.fact('b','Final year students appeared after verification',150)
        self.assertEqual(disagreements([a,b]),[])
        c=self.fact('c','Final year students qualified after verification',121)
        self.assertEqual(disagreements([a,c]),[[a,c]])

    def test_agreement_subcounts_have_explicit_different_bases(self):
        rows=[self.fact(str(n), label, value) for n,(label,value) in enumerate([
            ('National MoUs count',60),('International MoUs count',20),('Total industry MoUs signed',45)])]
        self.assertEqual(disagreements(rows),[])
        self.assertEqual(read_scope(rows[0])['sources']['count_basis'],'field_label')
        self.assertTrue(comparable(read_scope(rows[0]),read_scope(self.fact('other','National agreements count',61)))[0])

    def test_unknown_and_mixed_labels_do_not_suppress_disagreement(self):
        a=self.fact('a','Student count',120);b=self.fact('b','Student count',130)
        self.assertEqual(disagreements([a,b]),[[a,b]])
        self.assertEqual(count_basis('National and international agreements'),'')
        self.assertEqual(count_basis('Students appeared and passed'),'')
        self.assertTrue(comparable(read_scope(a),read_scope(self.fact('c','Students passed',130)))[0])

    def test_neighbouring_quote_and_arbitrary_include_labels_do_not_classify_measure(self):
        self.assertNotIn('count_basis',read_scope(self.fact('a','Enrollment records',120)))
        a=self.fact('a','Student count',120);b=self.fact('b','Student count',130)
        a.scope={'includes':['teaching staff']};b.scope={'includes':['faculty']}
        self.assertTrue(comparable(read_scope(a),read_scope(b))[0])


from .test_verification import VerificationBase
from apps.gaps.models import GapItem
from apps.scoring.capability.reviewed_evidence import snapshot, for_context, citation_issue


class ConflictSnapshotTests(VerificationBase):
    def create_pair(self, first='National MoUs count', second='International MoUs count'):
        quote='National agreements total 60; international agreements total 20 in 2024-25.'
        a=self._fact(field_key='agreements',field_name=first,value=60,source_snippet=quote)
        b=self._fact(field_key='agreements',field_name=second,value=20,source_snippet=quote)
        gap=GapItem.objects.create(sprint=self.sprint,gap_type='conflict',title='Recorded count conflict',source_fact=a)
        return a,b,gap,quote

    def test_field_wide_alternatives_are_complete_and_noncomparable_history_does_not_block(self):
        a,b,gap,quote=self.create_pair()
        ledger=snapshot(self.sprint)
        issue=next(i for i in ledger['issues'] if i['id']==str(gap.pk))
        self.assertEqual(set(issue['claim_ids']),{str(a.pk),str(b.pk)})
        self.assertEqual(issue['active_conflict_claim_ids'],[])
        self.assertEqual(issue['comparison_status'],'no_current_disagreement')
        source={'id':'p','document_id':str(self.doc.pk),'page_number':7,'text':quote}
        self.assertEqual(citation_issue([{'source_id':'p','quote':quote}],ledger,[source],state='met'),'')
        packet=for_context(ledger,[source])
        self.assertEqual(packet['issues'][0]['active_alternative_count'],0)
        gap.refresh_from_db();self.assertEqual(gap.status,'open')
        self.assertFalse(gap.events.exists())  # applicability is not a human resolution

    def test_genuine_same_measure_disagreement_keeps_both_alternatives_active(self):
        a,b,gap,quote=self.create_pair(second='National agreements count')
        ledger=snapshot(self.sprint)
        issue=next(i for i in ledger['issues'] if i['id']==str(gap.pk))
        self.assertEqual(set(issue['active_conflict_claim_ids']),{str(a.pk),str(b.pk)})
        source={'id':'p','document_id':str(self.doc.pk),'page_number':7,'text':quote}
        self.assertTrue(citation_issue([{'source_id':'p','quote':quote}],ledger,[source],state='met'))
