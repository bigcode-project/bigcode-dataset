from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from transformers import BertTokenizer, BertForTokenClassification, HfArgumentParser
from datasets import load_dataset
from datasets import Dataset
import torch

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
    batch_size: int = field(
        default=64,
        metadata={
            "help": "the batch size to use for inference"
        }
    )
    dataset_name: str = field(
        default='bigcode/pii-for-code-v2',
        metadata={
            "help": "Name of dataset to use for inference"
        }
    )
    job_id: int = field(
        default=0,
        metadata={
            "help": "job id for the data parallelism"
        }
    )
    output_path: str = field(
        default="processed_dataset",
        metadata={
            "help": "Path to save output entities"
        }
    )


def divide_list(lst, n):
    # Calculate the size of each part
    size = len(lst) // n
    
    # Divide the list into n equal parts using slicing
    result = [lst[i:i+size] for i in range(0, len(lst), size)]
    
    return result

    
def main():
    parser = HfArgumentParser(NerArguments)
    args = parser.parse_args()
    N_DEVICES = 4
    device = torch.device(args.job_id if torch.cuda.is_available() else "cpu")
    pipeline = PiiNERPipeline(args.model_name,
                            batch_size=args.batch_size,
                            window_size=512,
                            device=device,
                            num_workers=1,
                            use_auth_token=True)
    dataset = load_dataset(args.dataset_name, use_auth_token=True)['train']
    indices = np.arange(len(dataset))
    job_indices = divide_list(indices, N_DEVICES)
    dataset_job = dataset.select(job_indices[args.job_id])

    iterator = pipeline(dataset_job)
    processed_dataset_job = list(iterator)
    processed_dataset = Dataset.from_dict(pd.DataFrame(processed_dataset_job))
    processed_dataset.save_to_disk(f"{args.output_path}/job_{args.job_id}")


if __name__ == "__main__":
    main()