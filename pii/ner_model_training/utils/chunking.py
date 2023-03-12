import itertools
from typing import List, Iterable, Any

import numpy as np
from datasets import Dataset
from scipy.special import softmax
from tqdm.notebook import tqdm
from transformers import PreTrainedTokenizer
from transformers.trainer_utils import PredictionOutput

from utils.misc import LABEL2ID


def chunk_dataset(dataset: Dataset, tokenizer: PreTrainedTokenizer, overlap_freq: int = 0) -> Dataset:
    """
    Splits every entry in the `dataset` into chunks of the specific length.
    The maximum length of each chunk is set by the max_len_single_sentence attribute of the `tokenizer`.
    The `overlap_freq` argument controls the amount of overlap between adjacent chunks.
    If overlap_freq is 0, there is no overlap between chunks.
    If overlap_freq is 1, adjacent chunks overlap by half of their length.
    If overlap_freq is greater than 2, the overlap is set to a `1. / overlap_freq` fraction.

    The resulting dataset contains the following columns: `input_ids`, `attention_mask`, `labels`, `id`, and `chunk_id`.
    Each row in the dataset corresponds to a single chunk of the original data, identified by its `id` and `chunk_id`.
    """
    return Dataset.from_list(
        list(
            itertools.chain(
                *(chunk_inputs(**entry, tokenizer=tokenizer, max_length=tokenizer.max_len_single_sentence,
                               overlap_freq=overlap_freq) for entry in tqdm(list(dataset)))
            )
        )
    )


def chunk_inputs(input_ids,
                 attention_mask,
                 labels,
                 id,
                 *,
                 tokenizer,
                 max_length,
                 overlap_freq=0,
                 **kwargs):
    """
    Processes a sequence of `input_ids`, `attention_mask`, and `labels` by dividing it
    into smaller chunks to be processed by the model. The sequence is split into chunks
    of a specified maximum length, with a defined overlap frequency `overlap_freq`. The function
    handles special tokens that should be added to the beginning and end of the chunks.

    Returns
    -------
    list of dictionaries that contain the chunked `input_ids`, `attention_mask`, `labels`, and `chunk_id`

    """

    def _chunked_seq(seq: Iterable[Any], length: int, overlap_freq: int = 0):
        step = _get_chunking_step(length, overlap_freq)

        for i in range(len(seq) // step + 1):
            if i * step < len(seq):
                yield seq[i * step:i * step + length]

    chunks = zip(*[_chunked_seq(seq, max_length, overlap_freq) for seq in (input_ids, attention_mask, labels)])
    chunks = (_prepare_for_model(*chunk, tokenizer=tokenizer) for chunk in chunks)

    return [dict(input_ids=input_ids,
                 attention_mask=attention_mask,
                 labels=labels,
                 id=id,
                 chunk_id=i)
            for i, (input_ids, attention_mask, labels) in enumerate(chunks)]


def _prepare_for_model(input_ids: List[int], attention_mask: List[int], labels: List[int], *,
                       tokenizer: PreTrainedTokenizer, null_label_id: int = LABEL2ID['O']):
    input_ids = [tokenizer.cls_token_id] + list(input_ids) + [tokenizer.sep_token_id]
    attention_mask = [1] + list(attention_mask) + [1]
    labels = [null_label_id] + list(labels) + [null_label_id]

    return input_ids, attention_mask, labels


def _get_chunking_step(length: int, overlap_freq: int) -> int:
    """
    Computes the step size for chunking a sequence of a given length.

    Parameters
    ----------
    length : int
        Length of the sequence to chunk.
    overlap_freq : int
        Number of chunks to overlap. Default is 0, which means no overlap.
        If overlap_freq is 1, adjacent chunks overlap by half of their length.

    Returns
    -------
    int
        The chunking step size.
    """
    step = length
    if overlap_freq:
        if overlap_freq > 1:
            step = length // overlap_freq
        else:
            step = length // 2
    return step


def compose_chunk_predictions_with_samples(ref_dataset: Dataset, pred: PredictionOutput, entry_ids: List[int],
                                           tokenizer: PreTrainedTokenizer, overlap_freq: int = 2) -> Dataset:
    entry_ids = np.array(entry_ids)
    raw_pred_probas = [collate_pred_chunks(pred.predictions[entry_ids == i], tokenizer, overlap_freq=overlap_freq)
                       for i in sorted(set(entry_ids))]
    raw_true_labels = [collate_label_chunks(pred.label_ids[entry_ids == i], tokenizer, overlap_freq=overlap_freq)
                       for i in sorted(set(entry_ids))]

    # Remove ignored index
    mask = np.array(raw_true_labels) != -100
    pred_labels = np.array(raw_pred_probas)[mask]
    true_labels = np.array(raw_true_labels)[mask]
    #
    # pred_labels = [
    #     [p for (p, l) in zip(prediction, label) if l != -100]
    #     for prediction, label in zip(raw_pred_probas, raw_true_labels)
    # ]
    # true_labels = [
    #     [l for (p, l) in zip(prediction, label) if l != -100]
    #     for prediction, label in zip(raw_pred_probas, raw_true_labels)
    # ]

    ref_dataset = ref_dataset.map(lambda _, i: dict(labels=np.array(true_labels[i]), pred=np.array(pred_labels[i])),
                                  with_indices=True)
    return ref_dataset


def collate_pred_chunks(pred_chunks: np.ndarray, tokenizer: PreTrainedTokenizer, overlap_freq: int = 2) -> np.ndarray:
    """
    Takes in a tensor of predicted probabilities from the model and aggregates them across chunks.
    It normalizes the probabilities using softmax along the example axis.
    """
    step = _get_chunking_step(tokenizer.max_len_single_sentence, overlap_freq)
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


def collate_label_chunks(label_id_chunks: np.ndarray, tokenizer: PreTrainedTokenizer,
                         overlap_freq: int = 2) -> np.ndarray:
    """
    Takes in a tensor of true labels from the model and aggregates them across chunks.
    """
    step = _get_chunking_step(tokenizer.max_len_single_sentence, overlap_freq)
    # drop special tokens
    label_id_chunks = label_id_chunks[:, 1:-1]

    chunk_len = label_id_chunks.shape[1]
    length = chunk_len + (len(label_id_chunks) - 1) * step

    label_ids = -100 * np.ones(length, dtype=int)

    for i, chunk in enumerate(label_id_chunks):
        label_ids[i * step:i * step + len(chunk)] = chunk

    return label_ids
