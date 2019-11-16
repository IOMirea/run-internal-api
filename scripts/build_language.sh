#!/bin/sh

# Description:
#     This script takes language name as argument and builds corresponding docker image.
#
# Usage:
#     ./build_language.sh <language>
#
# Example:
#     ./build_language.sh python

if [ "$#" -ne 1 ]; then
  echo "Wrong number of arguments passsed" >&2
  exit 1
fi

docker build build -f build/$1.Dockerfile -t iomirea/run-lang-$1
docker push iomirea/run-lang-$1
