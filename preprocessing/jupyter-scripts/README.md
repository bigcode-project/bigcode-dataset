### Convert Jupyter Notebooks from The Stack v2 to Scripts

We reuse the same pipeline used in StarCoderdata with some tweaks to adapt to The Stack v2 and to correctly parse some notebooks in `nbformat 3`.

Note:

When installing `guesslang`, it requires `tensorflow` 2.5.0 but ypu will need to upgrade numpy to `1.20.3` for it to wrok with `datasets`