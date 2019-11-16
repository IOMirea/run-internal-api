#!/bin/bash

# Description:
#     This script detects what language images should be builded anb builds them.
#
# Usage:
#     ./build_all_images.sh <old_commit>
#
# Example:
#     ./build_all_images.sh 6d5651834cc6b0827e8934dd3e8aaa79bbda4ae5

set -e

if [ "$#" -ne 1 ]; then
  echo "Wrong number of arguments passsed" >&2
  exit 1
fi

to_update=$(scripts/detect_changes.sh $1 HEAD)

for language in $to_update
do
  echo building $language
  scripts/build_language.sh $language
done
