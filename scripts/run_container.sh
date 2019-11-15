#!/bin/sh

# Description:
#     This script runs docker container placing output to given directory
#
# Usage:
#     ./run_container.sh <language> <local folder> <host folder> <memory limit> <cpu limit> <code>
#
# Example:
#     ./run_container.sh python /results /runner_results 128m 0.5 'print("Hello world")'

set -e

if [ "$#" -ne 6 ]; then
  echo "Not enough arguments passsed" >&2
  exit 1
fi

random_name=$(cat /proc/sys/kernel/random/uuid)
new_folder=$2/$random_name
new_folder_host=$3/$random_name

mkdir $new_folder -p
echo $new_folder

CONTAINER_OUT_DIR=/out
IMAGE_NAME=iomirea/run-lang-$1

docker image inspect $IMAGE_NAME 1>/dev/null

echo "$6" > $new_folder/input

docker run --rm --network=none --memory=$4 --memory-swap=$4 --cpus=$5 \
           -v $new_folder_host:$CONTAINER_OUT_DIR \
           -v $new_folder_host/input:/input \
           -e OUT_DIR=$CONTAINER_OUT_DIR $IMAGE_NAME
