import itertools

import numpy as np
from datasets import Dataset
from scipy.special import softmax
from tqdm.notebook import tqdm
from transformers.trainer_utils import PredictionOutput

from utils.misc import LABEL2ID


def _prepare_for_model(input_ids, attention_mask, labels, *, tokenizer, null_label_id=LABEL2ID['O']):
    input_ids = [tokenizer.cls_token_id] + list(input_ids) + [tokenizer.sep_token_id]
    attention_mask = [1] + list(attention_mask) + [1]
    labels = [null_label_id] + list(labels) + [null_label_id]

    return input_ids, attention_mask, labels


def _get_chunking_step(length, overlap_freq):
    step = length
    if overlap_freq:
        if overlap_freq > 1:
            step = length // overlap_freq
        else:
            step = length // 2
    return step


def _chunked_seq(seq, length, overlap_freq=0):
    step = _get_chunking_step(length, overlap_freq)

    for i in range(len(seq) // step + 1):
        if i * step < len(seq):
            yield seq[i * step:i * step + length]


def chunk_inputs(input_ids,
                 attention_mask,
                 labels,
                 id,
                 *,
                 tokenizer,
                 max_length,
                 overlap_freq=0,
                 **kwargs):
    chunks = zip(*[_chunked_seq(seq, max_length, overlap_freq) for seq in (input_ids, attention_mask, labels)])
    chunks = (_prepare_for_model(*chunk, tokenizer=tokenizer) for chunk in chunks)

    return [dict(input_ids=input_ids,
                 attention_mask=attention_mask,
                 labels=labels,
                 id=id,
                 chunk_id=i)
            for i, (input_ids, attention_mask, labels) in enumerate(chunks)]


def chunk_dataset(dataset, tokenizer, overlap_freq=0):
    return Dataset.from_list(
        list(
            itertools.chain(
                *(chunk_inputs(**entry, tokenizer=tokenizer, max_length=tokenizer.model_max_length,
                               overlap_freq=overlap_freq) for entry in tqdm(list(dataset)))
            )
        )
    )


def collate_pred_chunks(pred_chunks, tokenizer, overlap_freq=2):
    step = _get_chunking_step(tokenizer.model_max_length, overlap_freq)
    # drop special tokens
    pred_chunks = pred_chunks[:, 1:-1]

    # logit normalization
    pred_chunks = softmax(pred_chunks, axis=-1)

    chunk_len = pred_chunks.shape[1]
    length = chunk_len + (len(pred_chunks) - 1) * step

    pred_proba = np.zeros((length, pred_chunks.shape[-1]))

    for i, chunk in enumerate(pred_chunks):
        pred_proba[i * step:i * step + len(chunk)] += (step / chunk_len) * chunk

    # normalization after aggregation
    pred_proba = pred_proba / pred_proba.sum(-1, keepdims=True)

    return pred_proba


def collate_label_chunks(label_id_chunks, tokenizer, overlap_freq=2):
    step = _get_chunking_step(tokenizer.model_max_length, overlap_freq)
    # drop special tokens
    label_id_chunks = label_id_chunks[:, 1:-1]

    chunk_len = label_id_chunks.shape[1]
    length = chunk_len + (len(label_id_chunks) - 1) * step

    label_ids = -100 * np.ones(length, dtype=int)

    for i, chunk in enumerate(label_id_chunks):
        label_ids[i * step:i * step + len(chunk)] = chunk

    return label_ids


def compose_chunk_predictions_with_samples(ref_dataset, pred: PredictionOutput, entry_ids, tokenizer, overlap_freq=2):
    entry_ids = np.array(entry_ids)
    raw_pred_probas = [collate_pred_chunks(pred.predictions[entry_ids == i], tokenizer, overlap_freq=overlap_freq)
                   for i in sorted(set(entry_ids))]
    raw_true_labels = [collate_label_chunks(pred.label_ids[entry_ids == i], tokenizer, overlap_freq=overlap_freq)
                   for i in sorted(set(entry_ids))]

    # Remove ignored index
    pred_labels = [
        [p for (p, l) in zip(prediction, label) if l != -100]
        for prediction, label in zip(raw_pred_probas, raw_true_labels)
    ]
    true_labels = [
        [l for (p, l) in zip(prediction, label) if l != -100]
        for prediction, label in zip(raw_pred_probas, raw_true_labels)
    ]

    ref_dataset = ref_dataset.map(lambda _, i: dict(labels=np.array(true_labels[i]), pred=np.array(pred_labels[i])),
                                  with_indices=True)
    return ref_dataset
