import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404, render_to_response, redirect
from django.utils.decorators import method_decorator

from extra_views import ModelFormSetView

from corpus.models import Relation, TextSegment, LabeledRelationEvidence, IEDocument
from corpus.forms import EvidenceForm


def next_segment_to_label(request, relation_id):
    relation = get_object_or_404(Relation, pk=relation_id)
    segment = relation.get_next_segment_to_label()
    if segment is None:
        return render_to_response('message.html',
                                  {'msg': 'There are no more evidence to label'})
    return redirect('corpus:label_evidence_for_segment', relation.pk, segment.pk)


def next_document_to_label(request, relation_id):
    relation = get_object_or_404(Relation, pk=relation_id)
    doc = relation.get_next_document_to_label()
    if doc is None:
        return render_to_response('message.html',
                                  {'msg': 'There are no more evidence to label'})
    return redirect('corpus:label_evidence_for_document', relation.pk, doc.pk)


def navigate_labeled_segments(request, relation_id, segment_id, direction):
    relation = get_object_or_404(Relation, pk=relation_id)
    segment = get_object_or_404(TextSegment, pk=segment_id)
    going_back = direction.lower() == 'back'
    segm_id_to_show = relation.neighbor_labeled_segments(segment.id, going_back)
    if segm_id_to_show is None:
        # Internal logic couldn't decide what other segment to show. Better to
        # forward to the one already shown
        messages.add_message(request, messages.WARNING,
                             'No other segment to show.')
        return redirect('corpus:label_evidence_for_segment', relation.pk, segment_id)
    else:
        if segm_id_to_show == segment.id:
            direction_str = "previous" if going_back else "next"
            messages.add_message(
                request, messages.WARNING,
                'No {0} segment to show.'.format(direction_str))
        return redirect('corpus:label_evidence_for_segment', relation.pk, segm_id_to_show)


class LabelEvidenceOnSegmentView(ModelFormSetView):
    template_name = 'corpus/segment_questions.html'
    form_class = EvidenceForm
    model = LabeledRelationEvidence
    extra = 0
    max_num = None
    can_order = False
    can_delete = False

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super(LabelEvidenceOnSegmentView, self).get_context_data(**kwargs)
        self.segment.hydrate()
        title = "Labeling Evidence for Relation {0}".format(self.relation)
        subtitle = 'For Document "{0}", Text Segment id {1}'.format(
            self.segment.document.human_identifier,
            self.segment.id)

        ctx.update({
            'title': title,
            'subtitle': subtitle,
            'segment': self.segment,
            'segment_rich_tokens': list(self.segment.get_enriched_tokens()),
            'relation': self.relation
        })
        return ctx

    def get_segment_and_relation(self):
        if hasattr(self, 'segment') and hasattr(self, 'relation'):
            return self.segment, self.relation
        self.segment = get_object_or_404(TextSegment, pk=self.kwargs['segment_id'])
        self.segment.hydrate()
        self.relation = get_object_or_404(Relation, pk=self.kwargs['relation_id'])
        self.evidences = list(self.segment.get_labeled_evidences(self.relation))
        return self.segment, self.relation

    def get_queryset(self):
        segment, relation = self.get_segment_and_relation()
        return super().get_queryset().filter(
            segment=self.segment, relation=self.relation
        )

    def get_success_url(self):
        return reverse('corpus:next_segment_to_label', args=[self.relation.pk])

    def formset_valid(self, formset):
        """
        If the formset is valid redirect to the supplied URL
        """
        messages.add_message(self.request, messages.INFO,
                             'Changes saved for segment {0}.'.format(self.segment.id))
        for form in formset:
            if form.has_changed():
                form.instance.judge = str(self.request.user)
        return super().formset_valid(formset)



class LabelEvidenceOnDocumentView(ModelFormSetView):
    template_name = 'corpus/document_questions.html'
    form_class = EvidenceForm
    model = LabeledRelationEvidence
    extra = 0
    max_num = None
    can_order = False
    can_delete = False

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super(LabelEvidenceOnDocumentView, self).get_context_data(**kwargs)
        title = "Labeling Evidence for Relation {0}".format(self.relation)
        subtitle = 'For Document "{0}"'.format(self.document.human_identifier)

        segments_with_rich_tokens = []
        for segment in self.document.get_text_segments():
            segment.hydrate()
            segments_with_rich_tokens.append(list(segment.get_enriched_tokens()))

        forms_values = []
        eos_propperties = {}
        relations_list = []
        for form_id, evidence in enumerate(self.evidences):
            left_eo_id = evidence.left_entity_occurrence.pk
            right_eo_id = evidence.right_entity_occurrence.pk
            relations_list.append({
                "relation": [left_eo_id, right_eo_id],
                "form_id": form_id,
            })

            forms_values.append({
                "value": False,
            })

            for eo_id in [left_eo_id, right_eo_id]:
                if eo_id not in eos_propperties:
                    eos_propperties[eo_id] = {
                        'selectable': True,
                        'selected': False,
                    }


        ctx.update({
            'title': title,
            'subtitle': subtitle,
            'segments': segments_with_rich_tokens,
            'relation': self.relation,
            'eos_propperties': json.dumps(eos_propperties),
            'relations_list': json.dumps(relations_list),
            'forms_values': json.dumps(forms_values),
        })
        return ctx

    def get_document_and_relation(self):
        if hasattr(self, 'document') and hasattr(self, 'relation'):
            return self.document, self.relation
        self.document = get_object_or_404(IEDocument, pk=self.kwargs['document_id'])
        self.relation = get_object_or_404(Relation, pk=self.kwargs['relation_id'])
        self.evidences = []
        for segment in self.document.get_text_segments():
            self.evidences.extend(
                list(segment.get_labeled_evidences(self.relation))
            )
        return self.document, self.relation

    def get_queryset(self):
        document, relation = self.get_document_and_relation()
        document_segments = document.get_text_segments()
        return super().get_queryset().filter(
            segment__in=document_segments, relation=self.relation
        )

    #def get_success_url(self):
    #    return reverse('corpus:start_labeling_evidence', args=[self.relation.pk])

    def formset_valid(self, formset):
        """
        If the formset is valid redirect to the supplied URL
        """
        messages.add_message(
            self.request, messages.INFO,
            'Changes saved for document {0}.'.format(self.document.id)
        )
        for form in formset:
            if form.has_changed():
                form.instance.judge = str(self.request.user)
        return super().formset_valid(formset)
