# source: https://github.com/mponty/bigcode-dataset/tree/main/pii/ner_model_training/utils by @mponty
import itertools
from tqdm import tqdm
from datasets import Dataset

def is_overlap(span, reference_span):
    l1, r1 = min(*span), max(*span)
    l2, r2 = min(*reference_span), max(*reference_span)
    return l1 <= l2 < r1 or l1 < r2 <= r1 or l2 <= l1 < r2 or l2 < r1 <= r2


def label_tokenized(
    entry, target_text="text", pii_column="fragments", LABEL2ID=None, IGNORE_CLASS=None
):
    content, pii = entry[target_text], entry[pii_column]

    if entry["offset_mapping"][-1] == (0, 0):
        entry["offset_mapping"][-1] = (len(content), len(content))

    entry["labels"] = [LABEL2ID["O"]] * len(entry["offset_mapping"])
    for entity in pii:
        if entity["category"] in IGNORE_CLASS:
            continue
        prefix = "B-"
        entity_span = tuple(entity["position"])
        for i, span in enumerate(entry["offset_mapping"]):
            if is_overlap(entity_span, span):
                label = prefix + entity["category"]
                entry["labels"][i] = LABEL2ID[label]
                prefix = "I-"

    return entry


def add_special_toks(entry, target_text, tokenizer):
    content = entry[target_text]
    entry["input_ids"] = (
        [tokenizer.cls_token_id] + entry["input_ids"] + [tokenizer.sep_token_id]
    )
    entry["attention_mask"] = [1] + entry["attention_mask"] + [1]
    entry["offset_mapping"] = (
        [(0, 0)] + entry["offset_mapping"] + [(len(content), len(content))]
    )
    entry["labels"] = [-100] + entry["labels"] + [-100]
    return entry


def tokenize_and_label_batch(
    entries,
    tokenizer,
    target_text="text",
    pii_column="fragments",
    LABEL2ID=None,
    IGNORE_CLASS=None,
):
    """Tokenize and label a batch of entries"""
    list_inputs = {
        k: [] for k in ["input_ids", "attention_mask", "offset_mapping", "labels"]
    }
    for text, fragments in zip(entries[target_text], entries[pii_column]):
        entry = {"text": text, "fragments": fragments}
        inputs = tokenizer.encode_plus(
            text, return_offsets_mapping=True, add_special_tokens=False
        )
        entry.update(inputs)
        entry = label_tokenized(
            entry,
            target_text=target_text,
            pii_column=pii_column,
            LABEL2ID=LABEL2ID,
            IGNORE_CLASS=IGNORE_CLASS,
        )
        entry = add_special_toks(entry, target_text=target_text, tokenizer=tokenizer)
        for k in list_inputs.keys():
            list_inputs[k].append(entry[k])
    return list_inputs


# Chunking
# we do all chunking with overlap_freq = 0


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
            yield seq[i * step : i * step + length]


def chunk_inputs(
    input_ids,
    attention_mask,
    labels,
    id,
    *,
    tokenizer,
    max_length,
    overlap_freq=0,
    **kwargs
):
    chunks = zip(
        *[
            _chunked_seq(seq, max_length, overlap_freq)
            for seq in (input_ids, attention_mask, labels)
        ]
    )
    return [
        dict(
            input_ids=input_ids,
            attention_mask=attention_mask,
            labels=labels,
            id=id,
            chunk_id=i,
        )
        for i, (input_ids, attention_mask, labels) in enumerate(chunks)
    ]


def chunk_dataset(dataset, tokenizer, overlap_freq=0):
    return Dataset.from_list(
        list(
            itertools.chain(
                *(
                    chunk_inputs(
                        **entry,
                        tokenizer=tokenizer,
                        max_length=tokenizer.model_max_length,
                        overlap_freq=overlap_freq
                    )
                    for entry in tqdm(list(dataset))
                )
            )
        )
    )
