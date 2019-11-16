#!/bin/bash

# Description:
#     This script detects which language images should be rebuilded and outputs language names.
#
# Usage:
#     ./detect_changes.sh <commit 1> <commit 2>
#
# Example:
#     ./detect_changes.sh 6d5651834cc6b0827e8934dd3e8aaa79bbda4ae5 59b2fc499a0439f4147077d761dfed99724a6902

set -e

if [ "$#" -ne 2 ]; then
  echo "Wrong number of arguments passsed" >&2
  exit 1
fi

DOCKERFILE_PATTERN="build/*.Dockerfile"
ENTRYPOINT_FILE=build/run_entrypoint.sh

updated_files=$(git diff --name-only "$1" "$2")

if [[ $updated_files =~ (^|[[:space:]])"$ENTRYPOINT_FILE"($|[[:space:]]) ]] ; then
  files_to_update=$(ls build/*.Dockerfile)
else
  files_to_update=$(echo "$updated_files" | grep "$DOCKERFILE_PATTERN" || true)
fi

for language in $files_to_update; do
  echo "${language:6:-11}"
done
