from nltk import RegexpTokenizer
import re

from utils.span_ops import remap_logits


def postprocess(pii_entry):
    start, end, old_value = pii_entry['start'], pii_entry['end'], pii_entry['value']
    new_value = old_value.lstrip('!"\'()*+,-./:;<=>?[\\]^_`{|}~')
    if pii_entry.get('tag') != 'KEY':
        new_value = re.sub(r'[\s\W]+$', '', new_value)
    new_value = new_value.strip()

    offset = old_value.find(new_value)
    pii_entry['start'] = start + offset
    pii_entry['end'] = pii_entry['start'] + len(new_value)
    pii_entry['value'] = new_value
    return pii_entry


def retokenize_with_logits(content, offset_mapping, pred, tokenizer_pattern=r'[\w+\.\-]+|[\S+]', **kwargs):
    """
    Re-tokenizes the `content` by RegexpTokenizer and aggregates `pred` logits for tokens which had been merged.

    Example:

    Let for next string:

        content = "\
        # Created by Big Koddy McModel <bigkoddy@examplemail.com>
        'SUPER_SECRET_KEY':'1234LjlkdslfKSLJDjd'"

    we have next tokenization and logits:
    ```
         #| Created| by| Big| Ko|ddy| Mc|Model| <|big|ko|ddy|@|example|mail|.|com|>| - tokens
         [    0    , 0 , 0.9, .8, .9, 1., 0.97, 0, .8,.9,.9,.9, 0.89  , 1. ,1.,1.,0] - logits

         '|SUPER|_|SEC|RET|_|KEY|'|:|'|1234|L|j|lk|d|s|lf|K|SL|JD|jd|'"
         [   0        ,...,    0     ,  .94 ,      ...           ,.96]
     ```

     then `retokenize_with_logits` transforms it into next:
     ```
         #| Created| by| Big| Koddy| McModel| <|bigkoddy|@|examplemail.com|> |'|SUPER_SECRET_KEY|'|:|'|1234LjlkdslfKSLJDjd|'
         [      0 ,  0, 0.9,  0.95,    0.98, 0,   0.99, .9,   0.9        , 0,0,        0       ,0,0,0,         0.98       ]
     ```

    """
    regtok = RegexpTokenizer(tokenizer_pattern)

    new_spans = list(regtok.span_tokenize(content))
    return dict(offset_mapping=new_spans, pred=remap_logits(new_spans, offset_mapping, pred))
