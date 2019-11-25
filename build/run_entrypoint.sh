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

INPUT=${INPUT:-""}
TIMEOUT=${TIMEOUT:-30}

if [ -z "$COMPILE_COMMAND" ]; then
  printf '%s' "$CODE" > exec_input
  COMPILE_COMMAND=true
else
  printf '%s' "$CODE" > compile_input
fi

if [ -n "$MERGE_OUTPUT" ]; then
    exec 2>&1
fi

script='
  eval "$COMPILE_COMMAND"
  printf "%s" "$INPUT" | "$@"
'

timeout --preserve-status --k=1s "$TIMEOUT" sh -e -c "$script" x "$@"
