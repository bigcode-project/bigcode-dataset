import argparse
import itertools
import json
from pprint import pprint

import numpy as np
import pandas as pd
from datasets import Dataset, DatasetDict, load_dataset, load_from_disk, load_metric
from huggingface_hub import notebook_login
from tqdm import tqdm
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)

from utils.preprocessing import chunk_dataset, tokenize_and_label_batch


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_ckpt", type=str, default="bigcode/bigcode-encoder")
    parser.add_argument(
        "--dataset_name",
        type=str,
        default="bigcode/pii-annotated-toloka-donwsample-emails",
    )
    parser.add_argument("batch_size", type=int, default=16)
    parser.add_argument("learning_rate", type=float, default=1e-5)
    parser.add_argument("lr_scheduler_type", type=str, default="cosine")
    parser.add_argument("num_train_epochs", type=int, default=3)
    parser.add_argument("weight_decay", type=float, default=0.01)
    parser.add_argument("gradient_checkpointing", action="store_true")
    parser.add_argument("output_dir", type=str, default="finetuned-encoder-pii")
    parser.add_argument("seed", type=int, default=0)
    parser.add_argument("num_proc", type=int, default=8)
    parser.add_argument("max_length", type=int, default=1024)
    parser.add_argument("debug", action="store_true")
    parser.add_argument("bf16", action="store_true")
    parser.add_argument("fp16", action="store_true")
    parser.add_argument("eval_freq", type=int, default=100)
    parser.add_argument("save_freq", type=int, default=1000)
    return parser.parse_args()


def get_stats(data):
    # get number of B-cat for cat in categories for each data split
    stats = {cat: 0 for cat in CATEGORIES}
    for entry in tqdm(data):
        for label in entry["labels"]:
            # only add labels for beginning with B-
            if label > 0 and ID2LABEL[label].startswith("B-"):
                stats[ID2LABEL[label][2:]] += 1
    return stats


def prepare_tokenizer(tokenizer):
    tokenizer.add_special_tokens({"pad_token": PAD_TOKEN})
    tokenizer.add_special_tokens({"sep_token": SEPARATOR_TOKEN})
    tokenizer.add_special_tokens({"cls_token": CLS_TOKEN})
    tokenizer.add_special_tokens({"mask_token": MASK_TOKEN})
    tokenizer.model_max_length = 1024
    return tokenizer


# Special tokens
MASK_TOKEN = "<mask>"
SEPARATOR_TOKEN = "<sep>"
PAD_TOKEN = "<pad>"
CLS_TOKEN = "<cls>"

# NER tags
CATEGORIES = [
    "NAME",
    "NAME_LICENSE",
    "NAME_EXAMPLE",
    "EMAIL",
    "EMAIL_LICENSE",
    "EMAIL_EXAMPLE",
    "USERNAME",
    "USERNAME_LICENSE",
    "USERNAME_EXAMPLE",
    "KEY",
    "IP_ADDRESS",
    "PASSWORD",
]
IGNORE_CLASS = ["AMBIGUOUS", "ID"]

LABEL2ID = {"O": 0}
for cat in CATEGORIES:
    LABEL2ID[f"B-{cat}"] = len(LABEL2ID)
    LABEL2ID[f"I-{cat}"] = len(LABEL2ID)
ID2LABEL = {v: k for k, v in LABEL2ID.items()}


def run_training(args, ner_dataset):
    print(f"Initializing Trainer...")

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        evaluation_strategy="steps",
        num_train_epochs=args.num_train_epochs,
        eval_steps=args.eval_freq,
        save_steps=args.save_freq,
        logging_steps=10,
        metric_for_best_model="f1",
        load_best_model_at_end=True,
        weight_decay=args.weight_decay,
        learning_rate=args.learning_rate,
        lr_scheduler_type=args.lr_scheduler_type,
        warmup_steps=args.num_warmup_steps,
        gradient_checkpointing=args.no_gradient_checkpointing,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        fp16=args.fp16,
        bf16=args.bf16,
        weight_decay=args.weight_decay,
        run_name=f"pii-bs{batch_size}-lr{lr}-wd{wd}-epochs{max_epochs}",
        report_to="wandb",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=ner_dataset["train"],
        eval_dataset=ner_dataset["validation"],
        data_collator=data_collator,
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
        callbacks=[
            EarlyStoppingCallback(
                early_stopping_patience=30, early_stopping_threshold=1e-3
            )
        ],
    )

    print("Training...")
    trainer.train()

    print("Saving last checkpoint of the model")
    model.save_pretrained(os.path.join(args.output_dir, "final_checkpoint/"))


def main(args):
    # load model and tokenizer
    model = AutoModelForTokenClassification.from_pretrained(
        args.model_ckpt,
        num_labels=len(ID2LABEL),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        use_auth_token=True,
        use_cache=not args.gradient_checkpointing,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model_ckpt, use_auth_token=True)
    tokenizer = prepare_tokenizer(tokenizer)

    # load dataset
    dataset = load_dataset(args.dataset_name, use_auth_token=True, split="train")
    dataset = dataset.remove_columns(["id"])
    dataset = dataset.add_column("id", range(len(dataset)))
    data = dataset.map(
        partial(
            tokenize_and_label_batch,
            tokenizer,
            target_text="text",
            pii_column="fragments",
            LABEL2ID=LABEL2ID,
            IGNORE_CLASS=IGNORE_CLASS,
        ),
        batched=True,
        batch_size=1000,
        num_proc=NUM_PROC,
    )

    # split to train and test
    data = data.train_test_split(test_size=0.2, shuffle=True, seed=args.seed)
    test_valid = data["test"].train_test_split(
        test_size=0.6, shuffle=True, seed=args.seed
    )
    train_data = data["train"]
    valid_data = test_valid["train"]
    test_data = test_valid["test"]
    test_data.to_json(f"{args.output_dir}/test_data.json")
    print("Test data saved to test_data.json")

    if args.debug:
        print(
            f"Train size {len(train_data)}\nValid size {len(valid_data)}\nTest size {len(test_data)}"
        )
        train_stats = get_stats(train_data)
        valid_stats = get_stats(valid_data)
        test_stats = get_stats(test_data)
        print("Train low-resource stats")
        # print stats for keys with less than 100 in teh value
        pprint({k: v for k, v in train_stats.items() if v < 300})
        print("Valid low-resource stats")
        pprint({k: v for k, v in valid_stats.items() if v < 100})
        print("Test low-resource stats")
        pprint({k: v for k, v in test_stats.items() if v < 100})

    print("Chunking the dataset...")
    data_collator = DataCollatorForTokenClassification(tokenizer=tokenizer)
    ner_dataset = DatasetDict(
        train=chunk_dataset(train_data, tokenizer),
        validation=chunk_dataset(valid_data, tokenizer),
        test=chunk_dataset(test_data, tokenizer),
    )
    print(ner_dataset)

    run_training(args, ner_dataset)


if __name__ == "__main__":
    args = get_args()
    set_seed(args.seed)
    os.makedirs(args.output_dir, exist_ok=True)

    logging.set_verbosity_error()

    main(args)
