langs=(solidity kotlin literate-agda julia java-server-pages isabelle idris lean powershell go erlang f-sharp ada pascal perl r protocol-buffer cmake sas ruby rust rmarkdown c-sharp smalltalk haskell maple mathematica ocaml makefile lua literate-coffeescript literate-haskell restructuredtext racket standard-ml systemverilog tex awk assembly alloy agda emacs-lisp dart cuda bluespec augeas batchfile tcsh stan scala tcl stata applescript shell clojure scheme antlr sparql sql glsl elm dockerfile cpp coffeescript common-lisp elixir groovy html java javascript markdown php python typescript verilog visual-basic vhdl thrift matlab yacc zig xslt json yaml)
# css prolog c fortran)
for language in "${langs[@]}"
do
    echo "Running lang $language"
    sbatch -J pii-$language infer.slurm $language 
done