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
class PipelineArgs:
    model_name: Optional[str] = field(default="./", metadata={"help": "the model name"})
    process_batch_size: int = field(default=10_000,  metadata={"help": "files per worker"}
    batch_size: Optional[int] = field(default=128, metadata={"help": "batch size"})
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
    
    out_dir = f"{args.out_path}{args.subset.strip('/').split('/')[-1]}"
    if accelerator.is_main_process:
        if not os.path.exists(out_dir):
            os.mkdir(out_dir)
                                  
    dataset = load_dataset(args.dataset, data_dir=args.subset, use_auth_token=True, split="train", num_proc=16)
    dataset = dataset.map(lambda example, idx: {"id": f"{idx}"}, with_indices=True, num_proc=16)
    
    model = AutoModelForTokenClassification.from_pretrained(args.model_name, use_auth_token=True)
    id_to_label = model.config.id2label
    tokenizer = AutoTokenizer.from_pretrained(args.model_name, use_auth_token=True)
    
    dataloader = DataLoader(dataset, batch_size=args.process_batch_size, shuffle=False, num_workers=4)
    
    model, dataloader = accelerator.prepare(model, dataloader)
    
    pipeline = PiiNERPipeline(
        model,
        tokenizer=tokenizer,
        batch_size=128,
        window_size=512,
        device=accelerator.local_process_index,
        num_workers=1,
        use_auth_token=True,
        id_to_label=id_to_label
    )
    for i, batch in enumerate(tqdm(dataloader)):
        iterator = pipeline(datasets.Dataset.from_dict(batch))
        result_iterator = list(iterator)
        processed_dataset = Dataset.from_dict(pd.DataFrame(result_iterator))
        processed_dataset.to_parquet(f"{args.out_path}/job_{accelerator.process_index}_{i}.parquet")

if __name__ == "__main__":
    main()
