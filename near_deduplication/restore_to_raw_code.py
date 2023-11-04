import os
import pandas as pd
import argparse
import shutil
from datasets import Dataset

def restore_files(input_path, output_path):
    # If output directory already exists, remove it
    if os.path.exists(output_path):
        shutil.rmtree(output_path)

    # Load the output dataset
    deduplicated_dataset = Dataset.load_from_disk(input_path)
    df = deduplicated_dataset.to_pandas()

    # Create a new directory to store the restored files
    os.makedirs(output_path, exist_ok=True)

    # Iterate over each example in the dataset
    for _, row in df.iterrows():
        file_path = os.path.join(output_path, row["file_path"])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)  # ensure the directory exists

        with open(file_path, "w", encoding="utf-8") as code_file:
            code_file.write(row["content"])

if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_path", help="Path to the input dataset.")
    parser.add_argument("--output_path", help="Path to the output directory.")
    args = parser.parse_args()

    # Run the function with the arguments
    restore_files(args.input_path, args.output_path)

# python3 restore_to_raw_code.py --input_path "output/deduplicated/ngram_5_num_perm_256_threshold_0.7/UnrealEngine" --output_path "output/restored/ngram_5_num_perm_256_threshold_0.7"
