import os
import pandas as pd
from datasets import Dataset
import logging
import argparse
import shutil

logging.basicConfig(level=logging.INFO)

def process_code_dir(input_dir, output_dir, exts):
    '''Transform the raw code into the format that is required by the 'load_dataset' function 
    from HuggingFace's 'datasets' library.'''

    # Create empty lists to store file paths and contents
    file_path_list = []  
    file_content_list = []
    file_count = 0

    csv_path = os.path.join(output_dir, 'converted.csv')
    pickle_dir = os.path.join(output_dir, 'converted')
    
    # If the files/directories exist, delete them
    if os.path.isfile(csv_path):
        os.remove(csv_path)
    if os.path.isdir(pickle_dir):
        shutil.rmtree(pickle_dir)

    logging.info("Starting to process the directory...")

    # Access all files within the directory
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            # Skip the file if its extension is not in the given list of extensions, unless exts is None
            if exts is not None and not any([file.endswith(ext) for ext in exts]):
                continue

            # Save each file's path
            file_path_list.append(os.path.join(root, file))
            
            # Save each file's content
            with open(os.path.join(root, file), 'r', errors='ignore') as f:
                file_content_list.append(f.read())
            file_count += 1
            if file_count % 1000 == 0:  # Adjust this number to your preference
                logging.info(f"Processed {file_count} files...")
    
    logging.info(f"Finished processing. Total {file_count} files have been processed.")

    # Convert the list into a DataFrame
    df = pd.DataFrame({'file_path':file_path_list, 'content':file_content_list})

    # Save DataFrame as a csv file
    #df.to_csv(csv_path, index=False)

    # Convert this pandas Dataframe into a Hugging Face's Dataset  
    dataset = Dataset.from_pandas(df)

    # Save Dataset as a pickle file
    dataset.save_to_disk(pickle_dir)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_dir', type=str, required=True)
    parser.add_argument('--output_dir', type=str, required=True)
    parser.add_argument('--ext', type=str, required=False, default=None)  # None or '.cpp,.h'
    
    args = parser.parse_args()
    exts = None if args.ext.lower() == 'none' else args.ext.split(',')
    process_code_dir(args.input_dir, args.output_dir, exts)

# python3 convert_raw_code_to_pickle.py --input_dir UnrealEngine --output_dir output --ext None
