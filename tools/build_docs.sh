#!/bin/sh
# Build the user guide and the equations reference into src/mbstudio/resources/.
# Run from anywhere: sh tools/build_docs.sh
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/docs"

version=$(sed -n 's/^version = "\(.*\)"/\1/p' "$root/pyproject.toml")
printf '\\newcommand{\\AppVersion}{%s}\n' "$version" > version.tex

for doc in user_guide eqs_ref; do
    latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build "$doc.tex"
done

cp build/user_guide.pdf "$root/src/mbstudio/resources/user_guide.pdf"
cp build/eqs_ref.pdf "$root/src/mbstudio/resources/equations_reference.pdf"
echo "Built version $version into src/mbstudio/resources/"
