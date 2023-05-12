import json
import nbformat
import jupytext
from glob import glob
from tqdm import tqdm
from guesslang import Guess
from datasets import load_dataset

# Function to load dataset and instantiate Guess
def load_data():
    guess = Guess()
    dataset = load_dataset("bigcode/the-stack", data_dir="data/jupyter-notebook", split="train")
    return guess, dataset

# Function to convert a notebook to a script and handle exceptions
def convert_notebook_to_script(nb, file_path):
    try:
        jupytext.write(nb, file_path)
    except:
        return False
    return True

# Function to convert dataset to script
def convert_to_script(dataset, success_dir, unknown_dir):
    for i in tqdm(range(len(dataset))):
        try:
            # Convert JSON content to nbformat notebook
            notebook = nbformat.from_dict(json.loads(dataset[i]["content"]))
            # Join cell sources
            for cell in notebook.cells:
                cell.source = "".join(cell.source)
            # Construct file path
            file_path = f"{success_dir}/{i}{notebook.metadata.language_info.file_extension}"
            # Try writing the notebook as a script
            if not convert_notebook_to_script(notebook, file_path):
                if "py" in str(notebook.metadata.kernelspec):
                    file_path = f"{success_dir}/{i}.py"
                else:
                    file_path = f"{unknown_dir}/{i}.ipynb"
                convert_notebook_to_script(notebook, file_path)
        except:
            # Log unreadable files
            with open("unreadable_files_index.txt","a+") as f:
                f.write(f"{i}\n")

# Function to convert unknown files
def convert_unknown_files(guess, success_dir, unknown_dir, lang2ext):
    for file in tqdm(glob(f"{unknown_dir}/*")):
        try:
            # Extract index from filename
            i = file.split("/")[-1].replace(".ipynb","")
            # Read notebook
            notebook = jupytext.read(file)
            # Set notebook metadata filter
            notebook.metadata["jupytext"] = {"notebook_metadata_filter": "-all"}
            # Extract code from notebook cells
            data = "\n".join([cell.source for cell in notebook.cells if cell.cell_type == 'code'])
            if not data.isspace():
                # Guess language of the code
                for p in guess.probabilities(data):
                    if p[1] >= 0.5:
                        try:
                            # Get file extension for the guessed language
                            ext = lang2ext[[lang for lang in lang2ext if lang in p[0].lower()][0]]
                            # Construct file path
                            file_path = f"{success_dir}/{i}{ext}"
                            # Write notebook as a script
                            convert_notebook_to_script(notebook, file_path)
                            break
                        except IndexError:
                            pass
        except:
            pass

if __name__ == "__main__":
    guess, dataset = load_data()
    lang2ext = {
        'qsharp': '.py', 'python': '.py', 'coconut': '.coco', 'R': '.r', 'julia': '.jl',
        'c++': '.cpp', 'scheme': '.scm', 'clojure': '.clj', 'bash': '.sh', 'powershell': '.ps1',
        'q': '.q', 'matlab': '.m', 'Wolfram Language': '.wolfram', 'idl': '.pro', 'javascript': '.js',
        'typescript': '.ts', 'scala': '.scala', 'rust': '.rs', 'robotframework': '.resource', 'csharp': '.cs',
        'fsharp': '.fs', 'sos': '.sos', 'java': '.java', 'groovy': '.groovy', 'sage': '.sage', 'ocaml': '.ml',
        'haskell': '.hs', 'tcl': '.tcl', 'maxima': '.mac', 'gnuplot': '.gp'
    }
    convert_to_script(dataset, "script", "unknown")
    convert_unknown_files(guess, "script", "unknown", lang2ext)
