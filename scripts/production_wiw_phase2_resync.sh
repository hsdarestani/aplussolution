#!/usr/bin/env bash
set -Eeuo pipefail

# WIW -> A+ migration is complete. This script intentionally does nothing so an
# old/manual workflow invocation can never overwrite locally edited A+ data.
echo "WIW reconciliation is retired; existing A+ data is preserved unchanged."
exit 0
