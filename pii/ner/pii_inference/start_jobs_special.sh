langs=(github-issues-filtered-structured) # (git-commits-cleaned jupyter-scripts-dedup-filtered  jupyter-structured-clean-dedup)

for language in "${langs[@]}"
do
    echo "Running lang $language"
    sbatch -J pii-$language infer_special.slurm $language 
done