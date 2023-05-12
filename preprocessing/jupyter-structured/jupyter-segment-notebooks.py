import json
import itertools
from datasets import load_dataset


def segment_blocks(content):
    
    cells = []
    cell_types = []
    for cell in content['cells']:
        if len(cell['source']) > 0:
            output = '_____no_output_____'
            if 'outputs' in cell.keys():
                if len(cell['outputs'])>0:
                    if 'text' in cell['outputs'][0].keys():
                        output = cell['outputs'][0]['text']
            cells.append([''.join(cell['source']),''.join(output)])
            cell_types.append(cell['cell_type'])
    return cells, cell_types


def segment(batch):
    try:
        content = json.loads(batch['content'])
        if 'py' in json.dumps(content['metadata']):
            cells, types = segment_blocks(content)

            cell_type_groups = [list(g) for k,g in itertools.groupby(types)]
            cell_types = [k for k,g in itertools.groupby(types)]
            cell_groups = []

            group_start = 0
            for g in cell_type_groups:
                cell_groups.append(cells[group_start:group_start+len(g)])
                group_start += len(g)

            batch['cells'] = cell_groups
            batch['cell_types'] = cell_types
            batch['cell_type_groups'] = cell_type_groups
            
        else:
            batch['cells'] = [[['empty']]]
            batch['cell_types'] = ['empty']
            batch['cell_type_groups'] = [['empty']]
        
    except:
        
        batch['cells'] = [[['empty']]]
        batch['cell_types'] = ['empty']
        batch['cell_type_groups'] = [['empty']]
        
    del batch['content']
    return batch


if __name__ == "__main__":
    
    # load dataset
    dataset = load_dataset("bigcode/the-stack",data_dir="data/jupyter-notebook", split="train",use_auth_token=True)
    # segment notebooks
    dataset = dataset.map(segment) 
    # filter out erronous cells via placeholders
    dataset = dataset.filter(lambda entry: entry['cell_types']!=['empty'])
    # push to hub
    dataset.push_to_hub("bigcode/jupyter-parsed")