#!/usr/bin/env python3
"""Compatibility shim for the read-only meter command."""
import sys

from meters import main


if __name__ == "__main__":
    sys.exit(main(["read", *sys.argv[1:]]))
