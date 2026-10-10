#!/bin/sh
set -eu

python -m scripts.init_chroma

exec "$@"
