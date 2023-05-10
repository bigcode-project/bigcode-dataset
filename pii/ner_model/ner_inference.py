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
from typing import Optional
from utils import PiiNERPipeline
import time

@dataclass
class PipelineArgs:
    model_name: Optional[str] = field(default="./", metadata={"help": "the model name"})
    process_batch_size: int = field(default=10_000,  metadata={"help": "files per worker"})
    batch_size: Optional[int] = field(default=1024, metadata={"help": "batch size"})
    dataset: Optional[str] = field(default="./", metadata={"help": "dataset"})
    subset: Optional[str] = field(default="data/python/", metadata={"help": "dataset subdirectory"})
    out_path: Optional[str] = field(default="./results/", metadata={"help": "path for output"})

        
def main():
    """launch code
    >>>> accelerate config
    >>>> accelerate launch ner_inference.py --process_batch_size=100000 --out_path=processed_dataset
    """
    parser = HfArgumentParser(PipelineArgs)
    args = parser.parse_args()

    accelerator = Accelerator()
    
    out_dir = f"{args.out_path}{args.subset.strip('/').split('/')[-2]}"
    if accelerator.is_main_process:
        if not os.path.exists(out_dir):
            os.mkdir(out_dir)
                                  
    dataset = load_dataset(args.dataset, data_dir=args.subset, use_auth_token=True, split="train", num_proc=12)
    dataset = dataset.map(
        lambda example, idx: {
            "id": f"{idx}",
            "max_stars_count": example["max_stars_count"] if example["max_stars_count"] is not None else 0
            }, 
            with_indices=True, num_proc=12)
    
    shard_size = (len(dataset))/8
    if shard_size > 1_000_000:
        process_batch_size = 200_000
    elif shard_size > 100_000:
        process_batch_size = 100_000
    else:
        process_batch_size = 10_000

    model = AutoModelForTokenClassification.from_pretrained(args.model_name, use_auth_token=True)
    id_to_label = model.config.id2label
    tokenizer = AutoTokenizer.from_pretrained(args.model_name, use_auth_token=True)
    
    columns = dataset.column_names
    dataset = dataset.remove_columns([col for col in  columns if col not in ["content", "id", "max_stars_repo_name", "max_stars_repo_path", "max_stars_count"]])

    dataloader = DataLoader(dataset, batch_size=process_batch_size, shuffle=False, num_workers=4)
    
    model, dataloader = accelerator.prepare(model, dataloader)
    
    pipeline = PiiNERPipeline(
        model,
        tokenizer=tokenizer,
        batch_size=args.batch_size,
        window_size=512,
        device=accelerator.local_process_index,
        num_workers=1,
        use_auth_token=True,
        id_to_label=id_to_label,
        window_overlap=False,
        bf16=True
    )
    num_samples = 0
    for i, batch in enumerate(tqdm(dataloader)):
        # last batches are filled - remove filling
        if i==len(dataloader)-1 and int(batch["id"][0])>int(batch["id"][-1]):
            for j in range(len(batch["id"])-1):
                if int(batch["id"][j])>int(batch["id"][j+1]):
                    stop_index = j+1
            for key in batch:
                batch[key] = batch[key][:stop_index]
        result = list(pipeline(datasets.Dataset.from_dict(batch)))
        
        # add original data
        for k, element in enumerate(result):
            for key in batch:
                element[key] = batch[key][k]
        
        processed_dataset = Dataset.from_dict(pd.DataFrame(result))
        processed_dataset.to_parquet(f"{out_dir}/job_{accelerator.process_index}_{i}.parquet")

if __name__ == "__main__":
    main()
