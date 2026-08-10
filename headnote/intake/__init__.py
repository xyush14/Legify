"""Client document intake — one write-only link per matter, with an approval gate.

See migrations/013_client_intake.sql for the safety reasoning behind the shape.
"""
from headnote.intake import storage  # noqa: F401

__all__ = ["storage"]
