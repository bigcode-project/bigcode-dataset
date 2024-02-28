import argparse
import os
from pprint import pprint

from datasets import DatasetDict, load_dataset
from tqdm import tqdm
from functools import partial
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
    set_seed,
    logging
)

from utils.preprocessing import chunk_dataset, tokenize_and_label_batch
from utils.eval import compute_metrics


# Special tokens
MASK_TOKEN = "<mask>"
SEPARATOR_TOKEN = "<sep>"
PAD_TOKEN = "<pad>"
CLS_TOKEN = "<cls>"

# NER tags
CATEGORIES = [
    "NAME",
    "EMAIL",
    "EMAIL_EXAMPLE",
    "USERNAME",
    "KEY",
    "IP_ADDRESS",
    "PASSWORD",
]
IGNORE_CLASS = ["AMBIGUOUS", "ID", "NAME_EXAMPLE", "USERNAME_EXAMPLE"]

LABEL2ID = {"O": 0}
for cat in CATEGORIES:
    LABEL2ID[f"B-{cat}"] = len(LABEL2ID)
    LABEL2ID[f"I-{cat}"] = len(LABEL2ID)
ID2LABEL = {v: k for k, v in LABEL2ID.items()}

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_ckpt", type=str, default="bigcode/bigcode-encoder")
    parser.add_argument(
        "--dataset_name",
        type=str,
        default="bigcode/pii-full-ds"
    )
    # addprefix to wandb run
    parser.add_argument("--prefix", type=str, default="")
    parser.add_argument("--add_not_curated", action="store_true")
    parser.add_argument("--train_batch_size", type=int, default=4)
    parser.add_argument("--eval_batch_size", type=int, default=4)
    parser.add_argument("--num_train_epochs", type=int, default=100)

    parser.add_argument("--learning_rate", type=float, default=1e-5)
    parser.add_argument("--lr_scheduler_type", type=str, default="cosine")
    parser.add_argument("--weight_decay", type=float, default=0.01)
    parser.add_argument("--warmup_steps", type=int, default=100)

    parser.add_argument("--gradient_checkpointing", action="store_true")
    parser.add_argument("--gradient_accumulation_steps", type=int, default=1)
    parser.add_argument("--eval_accumulation_steps", type=int, default=1)
    parser.add_argument("--num_proc", type=int, default=8)
    parser.add_argument("--bf16", action="store_true")
    parser.add_argument("--fp16", action="store_true")

    parser.add_argument("--local_rank", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--num_workers", type=int, default=8)
    parser.add_argument("--eval_freq", type=int, default=100)
    parser.add_argument("--save_freq", type=int, default=1000)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--output_dir", type=str, default="finetuned-encoder-pii")
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


def prepare_dataset(dataset, tokenizer, args):
    # tokenize and label
    dataset = dataset.map(
            partial(
                tokenize_and_label_batch,
                tokenizer=tokenizer,
                target_text="text",
                pii_column="fragments",
                LABEL2ID=LABEL2ID,
                IGNORE_CLASS=IGNORE_CLASS,
            ),
            batched=True,
            batch_size=1000,
            num_proc=args.num_workers,
        )
    return dataset

def run_training(args, ner_dataset, model, tokenizer):
    print(f"Initializing Trainer...")

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        evaluation_strategy="steps",
        num_train_epochs=args.num_train_epochs,
        per_device_train_batch_size=args.train_batch_size,
        per_device_eval_batch_size=args.eval_batch_size,
        eval_steps=args.eval_freq,
        save_steps=args.save_freq,
        logging_steps=10,
        metric_for_best_model="f1",
        load_best_model_at_end=True,
        weight_decay=args.weight_decay,
        learning_rate=args.learning_rate,
        lr_scheduler_type=args.lr_scheduler_type,
        warmup_steps=args.warmup_steps,
        gradient_checkpointing=args.gradient_checkpointing,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        eval_accumulation_steps=args.eval_accumulation_steps,
        fp16=args.fp16,
        bf16=args.bf16,
        run_name=f"{args.prefix}-bs{args.train_batch_size}-lr{args.learning_rate}-wd{args.weight_decay}-ep{args.num_train_epochs}-last",
        report_to="wandb",
    )


    data_collator = DataCollatorForTokenClassification(tokenizer=tokenizer)
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
                early_stopping_patience=15, early_stopping_threshold=1e-2
            )
        ],
    )

    print("Training...")
    #trainer.train()

    print("Saving last checkpoint of the model")
    #model.save_pretrained(os.path.join(args.output_dir, "final_checkpoint_last_exp/"))

    # evaluate on test set
    print("Evaluating on test set...")
    trainer.evaluate(ner_dataset["validation"])


def main(args):
    # load model and tokenizer
    model = AutoModelForTokenClassification.from_pretrained(
        #args.model_ckpt,
        "/fsx/loubna/code/bigcode-dataset/pii/ner/finetuned-encoder-pii/final_checkpoint-all-noexamples",
        num_labels=len(ID2LABEL),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        use_auth_token=True,
        use_cache=not args.gradient_checkpointing,
        output_hidden_states = False,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model_ckpt, use_auth_token=True)
    tokenizer = prepare_tokenizer(tokenizer)

    # load dataset
    dataset = load_dataset(args.dataset_name, use_auth_token=True)
    train_data = dataset["train"].shuffle(seed=args.seed)
    test_data = dataset["test"]
    valid_data = dataset["valid"]

    from datasets import concatenate_datasets
    train_data = concatenate_datasets([train_data, test_data])
    print(f"Concatenated train and test data, new train size: {len(train_data)}")


    if args.dataset_name == "bigcode/pii-full-ds":
        if not args.add_not_curated:
            print("Removing not curated data (-400 long files)...")
            # keep only curated data
            train_data = train_data.filter(lambda x: x["data_origin"] == "curated") 
        else:
            print("Keeping not curated data...")


    train_data = prepare_dataset(train_data, tokenizer, args)
    test_data = prepare_dataset(test_data, tokenizer, args)
    valid_data = prepare_dataset(valid_data, tokenizer, args)
    print(
        f"After tokenization:\nTrain size {len(train_data)}\nValid size {len(valid_data)}\nTest size {len(test_data)}"
    )

    if args.debug:
        train_stats = get_stats(train_data)
        valid_stats = get_stats(valid_data)
        test_stats = get_stats(test_data)
        print("Train low-resource stats")
        # print stats for keys with less than 100 in the value
        pprint({k: v for k, v in train_stats.items() if v < 300})
        print("Valid low-resource stats")
        pprint({k: v for k, v in valid_stats.items() if v < 100})
        print("Test low-resource stats")
        pprint({k: v for k, v in test_stats.items() if v < 100})


    print("Chunking the dataset...")
    ner_dataset = DatasetDict(
        train=chunk_dataset(train_data, tokenizer),
        validation=chunk_dataset(valid_data, tokenizer),
        test=chunk_dataset(test_data, tokenizer),
    )
    # remove columns
    ner_dataset = ner_dataset.remove_columns(["id", "chunk_id"])
    print(ner_dataset)

    run_training(args, ner_dataset, model, tokenizer)


if __name__ == "__main__":
    args = get_args()
    set_seed(args.seed)
    os.makedirs(args.output_dir, exist_ok=True)

    logging.set_verbosity_info()

    main(args)