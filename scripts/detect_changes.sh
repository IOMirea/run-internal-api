#!/bin/sh

# Description:
#     This script detects which language images should be rebuilded.
#
# Usage:
#     ./detect_changes.sh <commit 1> <commit 2>
#
# Example:
#     ./detect_changes.sh 4a5ff550632346ebd4c4c34898942a156e4d0302 c7fe22f6965db88fb4bc01671c3446835f33ed6e

if [ "$#" -ne 2 ]; then
  echo "Not enough arguments passsed" >&2
  exit 1
fi

DOCKERFILE_PATTERN=build/*.Dockerfile
ENTRYPOINT_FILE=run_entrypoint.sh

updated_files=$(git diff --name-only $1 $2)

if [[ $updated_files =~ (^|[[:space:]])"$ENTRYPOINT_FILE"($|[[:space:]]) ]] ; then
  ls build/*.Dockerfile
else
  echo updated_files | grep $DOCKERFILE_PATTERN
fi
