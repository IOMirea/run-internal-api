#!/bin/sh

# Description:
#     This script runs provided command with timeout sending output to directory.
#
# Env variables:
#     TIMEOUT:
#         Timeout for execution in seconds. Defaults to 30.
#     OUT_DIR:
#         Directory that is used for results such as stdout, stderr, execution time,
#         exit code.
#
# Usage:
#     ./run_entrypoint.sh <arguments>
#
# Example:
#     ./run_entrypoint.sh python main.py
#
# TODO: compilation

set -e

TIMEOUT=${TIMEOUT:-30}
OUT_DIR=${OUT_DIR:?Variable not set}

STDOUT_FILE=$OUT_DIR/stdout
STDERR_FILE=$OUT_DIR/stderr
EXEC_TIME_FILE=$OUT_DIR/exec_time
EXIT_CODE_FILE=$OUT_DIR/exit_code

# placeholder, it will not be overwritten if process exits successfully
exit_code=0

start_time=$(date +%s%03N)

# TODO: remove timeout usage. it comes with coreutils package
timeout --preserve-status --k=1s $TIMEOUT sh <<EOT || exit_code=$?
  $@ 1> $STDOUT_FILE 2> $STDERR_FILE
EOT

end_time=$(date +%s%03N)

echo $exit_code > $EXIT_CODE_FILE
echo $((end_time-start_time)) > $EXEC_TIME_FILE
