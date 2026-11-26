#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
if [ -x .venv/bin/python ]; then
    default_python=.venv/bin/python
else
    default_python=python3
fi
exec "${PYTHON:-$default_python}" -m src.main "$@"
