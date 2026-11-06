#!/bin/sh
# What the container runs.
#
# Thin on purpose. Everything that needs judgement - finding the code, working
# out which user to be, installing Pillow once - is in run.py, where it is
# Python and can be tested. This exists only because a compose `command:` is a
# nicer thing to point at a shell script than at a Python file.
exec python "$(dirname "$0")/run.py"
