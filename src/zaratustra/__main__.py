"""Explicit installed-Python fallback for the same console entry point."""

from zaratustra.cli import main

raise SystemExit(main())
