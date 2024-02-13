import json
import os
import tempfile

import jupytext
import nbformat
from datasets import load_dataset, concatenate_datasets

from guesslang import Guess


def dump_and_extract_text(notebook, file_name):
    """Convert notebook to script and save it in a temp file then exctarct text, thsi is needed for jupytext
    This might fail during conversion"""
    temp_dir = tempfile.gettempdir()
    temp_file_name = os.path.join(temp_dir, file_name)
    try:
        jupytext.write(notebook, temp_file_name)
        with open(temp_file_name, "r") as fp:
            text = fp.read()
        return True, text
    except:
        return False, ""


def get_file_name_and_extension(notebook):
    try:
        extension = notebook.metadata.language_info.file_extension
        return f"file{extension}", extension
    except (AttributeError, KeyError):
        if "py" in str(getattr(notebook.metadata, "kernelspec", "")):
            return f"file.py", ".py"
        return f"file.ipynb", ".ipynb"


def convert_nbformat3_to4(json_content):
    """Some notebooks are nbformat 3, we convert them to nbformat 4 so that we can use jupytext"""
    notebook = nbformat.from_dict(json_content)
    new_nb = nbformat.v4.convert.upgrade(notebook, from_version=3, from_minor=0)
    return new_nb


def convert_nb_script(examples):
    scripts = []
    extensions = []
    nbformats = []
    for content in examples["content"]:
        extension, text = "", ""
        nbformat3 = False
        try:
            json_content = json.loads(content)
            # Convert JSON content to nbformat notebook
            if json_content["nbformat"] == 3:
                notebook = convert_nbformat3_to4(json_content)
                nbformat3 = True
            else:
                notebook = nbformat.from_dict(json_content)
            # Join cell sources
            for cell in notebook.cells:
                cell.source = "".join(cell.source)
            file_name, extension = get_file_name_and_extension(notebook)
            _, text = dump_and_extract_text(notebook, file_name)
        except Exception as e:
            pass
        scripts.append(text)
        extensions.append(extension)
        nbformats.append(nbformat3)
    return {"script": scripts, "conversion_extension": extensions, "is_nbformat_3": nbformats}


def get_size_text(example):
    return {"size": len(example["content"])}

lang2ext = {
    "qsharp": ".py",
    "python": ".py",
    "coconut": ".coco",
    "R": ".r",
    "julia": ".jl",
    "c++": ".cpp",
    "scheme": ".scm",
    "clojure": ".clj",
    "bash": ".sh",
    "powershell": ".ps1",
    "q": ".q",
    "matlab": ".m",
    "Wolfram Language": ".wolfram",
    "idl": ".pro",
    "javascript": ".js",
    "typescript": ".ts",
    "scala": ".scala",
    "rust": ".rs",
    "robotframework": ".resource",
    "csharp": ".cs",
    "fsharp": ".fs",
    "sos": ".sos",
    "java": ".java",
    "groovy": ".groovy",
    "sage": ".sage",
    "ocaml": ".ml",
    "haskell": ".hs",
    "tcl": ".tcl",
    "maxima": ".mac",
    "gnuplot": ".gp",
}
guess = Guess()

def convert_failed_nb_script(examples):
    """Convert notebooks whose extension/language identification failed in the previous function"""
    scripts = []
    extensions = []
    for content, extension in zip(examples["content"], examples["conversion_extension"]):
        # Convert JSON content to nbformat notebook
        json_content = json.loads(content)
        if json_content["nbformat"] == 3:
            notebook = convert_nbformat3_to4(json_content)
        else:
            notebook = nbformat.from_dict(json_content)
        # Join cell sources
        for cell in notebook.cells:
            cell.source = "".join(cell.source)
        # Set notebook metadata filter
        notebook.metadata["jupytext"] = {"notebook_metadata_filter": "-all"}
        # Extract code from notebook cells
        data = "\n".join(
            [cell.source for cell in notebook.cells if cell.cell_type == "code"]
        )
        ext, text = "", ""
        if not data.isspace():
            # Guess language of the code
            for p in guess.probabilities(data):
                if p[1] >= 0.5:
                    try:
                        # Get file extension for the guessed language
                        ext = lang2ext[
                            [lang for lang in lang2ext if lang in p[0].lower()][0]
                        ]
                        # Construct file path
                        file_name = f"file{ext}"
                        # Write notebook as a script
                        _, text = dump_and_extract_text(notebook, file_name)
                        break
                    except IndexError:
                        pass
        scripts.append(text)
        extension = ext if ext else extension
        extensions.append(extension)
    return {"script": scripts, "conversion_extension": extensions}


if __name__ == "__main__":
    dataset = load_dataset("bigcode/stack_v2_notebooks_small", split="train", num_proc=22)
    print(f"Initial number of samples: {len(dataset)}")
    # multiprocessing seems to give incorrect results
    dataset = dataset.map(convert_nb_script, batched=True, batch_size=2_000)
    nbformat3 = dataset.filter(lambda x: x["is_nbformat_3"])
    print(f"Number of nbformat 3 samples: {len(nbformat3)}, percentage compared to the whole dataset: {len(nbformat3) * 100 / len(dataset)}%")

    # samples that need fixing
    valid_samples = dataset.filter(lambda x: x["conversion_extension"] != ".ipynb" and x["script"] != "")
    print(f"Number of valid converted scripts: {len(valid_samples)}, makes up: {len(valid_samples) * 100 / len(dataset)}% of teh whole dataset")
    invalid_samples = dataset.filter(lambda x: x["conversion_extension"] == ".ipynb")
    print(f"Fixing {len(invalid_samples)} invalid samples ({len(invalid_samples) * 100 / len(dataset)}%)")
    invalid_samples_fixed = invalid_samples.map(convert_failed_nb_script, batched=True, batch_size=2_000)
    # .ipynb extension means the notebook wasn't properly parsed to script
    fixed_samples = invalid_samples_fixed.filter(lambda x: x["conversion_extension"] != ".ipynb" and x["script"] != "")
    print(f"We fixed {len(fixed_samples)} samples ({len(fixed_samples) * 100 / len(dataset)}%)")

    # concatenate datasets
    final_dataset = concatenate_datasets([valid_samples, fixed_samples])
    final_dataset = final_dataset.map(get_size_text, num_proc=36)
    print(f"Final dataset size: {len(final_dataset)} files and {sum(final_dataset['size']) / 10**9}GB of text")
    final_dataset.push_to_hub("stack_v2_notebooks_small_scripts")
