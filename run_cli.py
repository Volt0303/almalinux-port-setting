#!/usr/bin/env python3
"""PyInstaller entry point for the headless CLI."""
import sys

from ipset.cli import main

if __name__ == "__main__":
    sys.exit(main())
