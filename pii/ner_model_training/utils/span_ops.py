from collections import defaultdict
from seqeval.metrics.sequence_labeling import get_entities
import numpy as np

from utils.misc import ID2LABEL, LABEL2ID



def is_overlap(span, reference_span):
    l1, r1 = min(*span), max(*span)
    l2, r2 = min(*reference_span), max(*reference_span)
    return l1<=l2<r1 or l1<r2<=r1 or l2<=l1<r2 or l2<r1<=r2


def tokenize_and_label(entry, tokenizer):
    inputs = tokenizer.encode_plus(entry['content'], return_offsets_mapping=True, add_special_tokens=False)
    entry.update(inputs)
    return label_tokenized(entry)


def label_tokenized(entry, pii_column='pii'):
    content, pii = entry['content'], entry[pii_column]

    if entry['offset_mapping'][-1] == (0, 0):
        entry['offset_mapping'][-1] = (len(content), len(content))

    entry['labels'] = [LABEL2ID['O']] * len(entry['offset_mapping'])
    for entity in pii:
        prefix = 'B-'
        entity_span = (entity['start'], entity['end'])
        for i, span in enumerate(entry['offset_mapping']):
            if is_overlap(entity_span, span):
                label = prefix + entity['tag']
                entry['labels'][i] = LABEL2ID[label]
                prefix = 'I-'
    return entry


def convert_labels(entry):
    pred = np.array(entry['pred'])
    pred_labels = np.argmax(pred, axis=-1)
    pred_labels = [ID2LABEL[l] for l in pred_labels]
    label_prob = np.max(pred, axis=-1)

    pred_entities = get_entities([pred_labels])

    text, spans = entry['content'], entry['offset_mapping']
    predicted_pii = [dict(
        tag=tag,
        value=text[spans[start_idx][0]:spans[end_idx][-1]],
        start=spans[start_idx][0],
        end=spans[end_idx][-1],
        confidence=np.mean(label_prob[start_idx:(end_idx + 1)])
    )
        for tag, start_idx, end_idx in pred_entities]
    return dict(predicted_pii=predicted_pii)


def map_spans(new_spans, old_spans):
    new_cursor = enumerate(span[-1] for span in new_spans)
    old_cursor = enumerate(span[-1] for span in old_spans)

    i, j = 0, 0
    curr_new = curr_old = (0, 0)
    mapping = defaultdict(list)

    while (j < len(new_spans)) or (i < len(old_spans)):

        if curr_new < curr_old:
            try:
                j, curr_new = next(new_cursor)
            except StopIteration:
                j = len(new_spans)
        elif curr_new > curr_old:
            try:
                i, curr_old = next(old_cursor)
            except StopIteration:
                i = len(old_spans)
        else:
            try:
                j, curr_new = next(new_cursor)
            except StopIteration:
                j = len(new_spans)

            try:
                i, curr_old = next(old_cursor)
            except StopIteration:
                i = len(old_spans)

        if (j < len(new_spans)) and (i < len(old_spans)):
            mapping[j].append(i)

    return mapping


def remap_logits(new_spans, old_spans, old_logits):
    mapping = map_spans(new_spans, old_spans)
    mapping_iter = [mapping[i] for i in range(len(mapping))]
    new_logits = [np.mean([old_logits[j] for j in indices], axis=0) for indices in mapping_iter]
    return np.array(new_logits)


def _exclude_overlaps(spans, ref_spans):
    return [span for span in spans if not any([is_overlap(span, ref) for ref in ref_spans])]


def exclude_pii_overlap(entry):
    pii_spans = [(entity['start'], entity['end']) for entity in entry['pii']]
    return dict(
        predicted_pii=[ent for ent in entry['predicted_pii']
                       if not any([is_overlap((ent['start'], ent['end']), ref) for ref in pii_spans])]
    )
