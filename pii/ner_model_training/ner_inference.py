import os
from dataclasses import dataclass, field
from tqdm import tqdm

import pandas as pd
import torch
from torch.utils.data import DataLoader
import datasets
from datasets import load_dataset, Dataset
from accelerate import Accelerator
from transformers import HfArgumentParser
from transformers import AutoModelForTokenClassification, AutoTokenizer

from utils import PiiNERPipeline


@dataclass
class NerArguments:

    """configuration for running NER model inference
    """
    model_name: str = field(
        default='bigcode/bigcode-encoder-pii-ner',
        metadata={
            "help": "Name of model to use for inference"
        }
    )
    process_batch_size: int = field(
        default=100,
        metadata={
            "help": "the batch size to dispatch to each job"
        }
    )

    dataset_name: str = field(
        default='bigcode/pii-for-code-v2',
        metadata={
            "help": "Name of dataset to use for inference"
        }
    )
    out_path: str = field(
        default="processed_dataset",
        metadata={
            "help": "dir to save output dataset"
        }
    )

def main():
    """launch code
    >>>> accelerate config
    >>>> accelerate launch ner_inference.py --process_batch_size=100000 --out_path=processed_dataset
    """
    parser = HfArgumentParser(NerArguments)
    args = parser.parse_args()

    accelerator = Accelerator()
    if accelerator.is_main_process:
        out_dir = f"{args.out_path}"
        if not os.path.exists(out_dir):
            os.mkdir(out_dir)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dataset = load_dataset(args.dataset_name, use_auth_token=True, split="train")
    model = AutoModelForTokenClassification.from_pretrained(args.model_name, use_auth_token=True).to(device)
    id_to_label = model.config.id2label
    tokenizer = AutoTokenizer.from_pretrained(args.model_name, use_auth_token=True)
    dataloader = DataLoader(dataset, batch_size=args.process_batch_size, shuffle=False, num_workers=4)
    model, dataloader = accelerator.prepare(model, dataloader)
    pipeline = PiiNERPipeline(
        model,
        tokenizer=tokenizer,
        batch_size=128,
        window_size=512,
        device=accelerator.local_process_index if torch.cuda.is_available() else device,
        num_workers=1,
        use_auth_token=True,
        id_to_label=id_to_label
    )
    for i, batch in tqdm(enumerate(dataloader)):
        iterator = pipeline(datasets.Dataset.from_dict(batch))
        result_iterator = list(iterator)
        processed_dataset = Dataset.from_dict(pd.DataFrame(list(result_iterator)))
        processed_dataset.to_parquet(f"{args.out_path}/job_{accelerator.process_index}_{i}.parquet")

if __name__ == "__main__":
    main()
