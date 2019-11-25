#!/bin/sh

# Description:
#     This script runs provided command with timeout.
#
# Env variables:
#     CODE:
#         Source code.
#     INPUT:
#         Stdin.
#     COMPILE_COMMAND:
#         Compilation command. Should output result from `compile_input` to `exec_input`.
#     TIMEOUT:
#         Timeout for execution in seconds. Defaults to 30.
#     MERGE_OUTPUT:
#         Merges stdout and stderr in stdout if set.
#
# Usage:
#     ./run_entrypoint.sh <arguments>
#
# Example:
#     ./run_entrypoint.sh python main.py
#

set -e

TIMEOUT=${TIMEOUT:-30}

if [ -z "$COMPILE_COMMAND" ]; then
  echo "$CODE" > exec_input
  COMPILE_COMMAND=true
else
  echo "$CODE" > compile_input
fi

export COMPILE_COMMAND

if [ -n "$MERGE_OUTPUT" ]; then
    exec 2>&1
fi

script='$COMPILE_COMMAND; "$@"'

timeout --preserve-status --k=1s "$TIMEOUT" printf "%s" "$INPUT" | sh -e -c "$script" x "$@"
