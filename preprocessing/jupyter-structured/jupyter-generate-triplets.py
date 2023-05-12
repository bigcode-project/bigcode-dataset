import json
import itertools
from datasets import load_dataset, load_from_disk, Dataset
import re
from tqdm import tqdm
import sys

def clean_markdown(text):
    text = re.sub(r'<.*?>','',text)
    text = re.sub(r'\n+','',text)
    text = text.replace('#','')
    return text


def parse_data(ds):
    """Parse data into markdown-code pairs"""
   
    for notebook in tqdm(ds):
        
        types = notebook["cell_types"]
        cells = notebook["cells"]
        
        if len(types)>0:
            if types[0] == "code":
                # drop first cell of code to have the notebook start with markdown
                cells = cells[1:]
                types = types[1:]
            #else:
                # drop first the two cells of markdown followed by code
                # the first markown cell of a notebook is often a long description of the whole notebook
            #    cells = notebooks["cells"][2:]
            #    types = notebooks["types"][2:]
            if len(types)>0:
                if types[-1] == 'markdown':
                    cells = cells[:-1]
                    types = types[:-1]

                if len(cells) % 2 == 0:
                    inner_markdowns = [cells[j] for j in range(len(cells)) if j % 2 == 0]
                    inner_code_snippets = [cells[j+1] for j in range(len(cells) - 1) if j % 2 == 0]


                    for markdown_block, code_snippet in zip(inner_markdowns,inner_code_snippets):
                        markdown_block = ' '.join([clean_markdown(block[0]) for block in markdown_block])
                        code = '\n'.join([snippet[0] for snippet in code_snippet])
                        output = [snippet[1] for snippet in code_snippet][-1]

                        line = {'markdown':markdown_block,
                                'code':code,
                                'output':output,
                                'license':notebook['max_issues_repo_licenses'][0],
                                'path':notebook['max_stars_repo_path'],
                                'repo_name':notebook['max_stars_repo_name'],
                                }
                        yield line

                        
if __name__ == "__main__":
    file = sys.argv[1]
    
    dataset = load_dataset("bigcode/jupyter-parsed")
    with open(file,'w') as out:
        for line in parse_data(data):
            out.write(json.dumps(line)+'\n')

    dataset = load_dataset('json',ata_files=file)
    
    dataset.push_to_hub("bigcode/jupyter-code-text-pairs")   
