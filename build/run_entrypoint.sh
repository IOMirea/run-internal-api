#!/bin/sh

# Description:
#     This script runs provided command with timeout.
#
# Env variables:
#     INPUT:
#         Source code.
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
  echo "$INPUT" > exec_input
else
  echo "$INPUT" > compile_input
fi

exit_code=0

timeout --preserve-status --k=1s "$TIMEOUT" sh <<EOT || exit_code=$?
  run_user_code() {
    $COMPILE_COMMAND
    $@
  }

  if [ -z "$MERGE_OUTPUT" ]; then
    run_user_code
  else
    run_user_code 2>&1
  fi
EOT

# reserved docker run/start exit codes
# 125 -> 253
# 126 -> 254
# 127 -> 255
case $exit_code in
  125) return 253
  ;;
  126) return 254
  ;;
  127) return 255
  ;;
esac

exit $exit_code
