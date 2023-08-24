import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datasets import load_dataset, DatasetDict
from transformers import (
    AutoTokenizer,
    AutoModelForTokenClassification,
    TrainingArguments,
    Trainer,
    DataCollatorForTokenClassification,
    HfArgumentParser,
    EarlyStoppingCallback
)

from utils import compute_metrics, label_tokenized, chunk_dataset, LABEL2ID, ID2LABEL

logger = logging.getLogger(__name__)


@dataclass
class ModelArguments:
    model_name_or_path: str = field(
        metadata={"help": "Path to pretrained model or model identifier from huggingface.co/models"}
    )

    cache_dir: Optional[str] = field(
        default=None,
        metadata={"help": "Where do you want to store the pretrained models downloaded from huggingface.co"},
    )

    early_stopping_patience: int = field(
        default=1,
    )

    early_stopping_threshold: int = field(
        default=1e-3,
    )


@dataclass
class DataTrainingArguments:
    train_dataset: str = field(
        default="bigcode/pseudo-labeled-python-data-pii-detection-filtered",
        metadata={"help": "The train dataset"}
    )

    dev_dataset: str = field(
        default="bigcode/pii-for-code-v2",
        metadata={"help": "The validation dataset"}
    )

    max_seq_length: int = field(
        default=512,
        metadata={
            "help": (
                "The maximum input sequence length after tokenization. Sequences longer "
                "than this will be chunked into pieces of this length."
            )
        },
    )


def main():
    parser = HfArgumentParser((ModelArguments, DataTrainingArguments, TrainingArguments))

    model_args, data_args, training_args = parser.parse_args_into_dataclasses()

    model = AutoModelForTokenClassification.from_pretrained(
        model_args.model_name_or_path,
        cache_dir=model_args.cache_dir,
        num_labels=len(ID2LABEL)
    )
    tokenizer = AutoTokenizer.from_pretrained(
        model_args.model_name_or_path,
        cache_dir=model_args.cache_dir,
        add_prefix_space=True)

    model.config.id2label = {str(i): label for i, label in enumerate(ID2LABEL)}
    model.config.label2id = LABEL2ID

    tokenizer.model_max_length = data_args.max_seq_length

    train_dataset = load_dataset(data_args.train_dataset, use_auth_token=True)['train']
    dev_dataset = load_dataset(data_args.dev_dataset, use_auth_token=True)['train']

    def tokenize_and_label(entry, tokenizer=tokenizer):
        inputs = tokenizer.encode_plus(entry['content'], return_offsets_mapping=True, add_special_tokens=False)
        entry.update(inputs)
        return label_tokenized(entry)

    dev_dataset = dev_dataset.map(lambda x: dict(pii=json.loads(x['pii'])))
    dev_dataset = dev_dataset.map(tokenize_and_label)

    train_dataset = train_dataset.map(lambda x: dict(pii=json.loads(x['pii'])))
    train_dataset = train_dataset.map(tokenize_and_label, num_proc=8)
    train_dataset = chunk_dataset(train_dataset, tokenizer)

    ner_dataset = DatasetDict(
        train=train_dataset,
        validation=chunk_dataset(dev_dataset, tokenizer),
    )

    trainer = Trainer(
        model,
        training_args,
        train_dataset=ner_dataset["train"],
        eval_dataset=ner_dataset["validation"],
        data_collator=DataCollatorForTokenClassification(tokenizer),
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=model_args.early_stopping_patience,
                                         early_stopping_threshold=model_args.early_stopping_threshold)]
    )

    trainer.train()
