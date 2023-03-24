from dataclasses import dataclass, field
from tqdm import tqdm
import torch
from torch.utils.data import DataLoader
import datasets 
from datasets import load_dataset
from accelerate import Accelerator, DistributedType
from transformers import BertTokenizer, BertForTokenClassification, HfArgumentParser
from transformers import is_torch_available, AutoModelForTokenClassification, AutoTokenizer, \
    DataCollatorForTokenClassification

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
    job_batch_size: int = field(
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
    output_path: str = field(
        default="processed_dataset",
        metadata={
            "help": "Path to save output entities"
        }
    )

def main():
    """launch code
    >>>> accelerate config
    >>>> accelerate launch accelerate_pii_bert.py --dryrun=False --batch_size=128 --output=output.json
    """
    parser = HfArgumentParser(NerArguments)
    args = parser.parse_args()

    accelerator = Accelerator()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dataset = load_dataset(args.dataset_name, use_auth_token=True, split="train")
    model = AutoModelForTokenClassification.from_pretrained(args.model_name, use_auth_token=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model_name, use_auth_token=True)
    dataloader = DataLoader(dataset, batch_size=args.job_batch_size, shuffle=False)
    model, dataloader = accelerator.prepare(model, dataloader)
    pipeline = PiiNERPipeline(
        model,
        tokenizer=tokenizer,
        batch_size=64,
        window_size=512,
        device=device,
        num_workers=1,
        use_auth_token=True
    )
    for batch in tqdm(dataloader):
        iterator = pipeline(datasets.Dataset.from_dict(batch))
        processed_dataset_job = list(iterator)


if __name__ == "__main__":
    main()
