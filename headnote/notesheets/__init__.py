"""Hearing note sheets + per-hearing preparation state.

The note sheet is what a junior hands the senior before a hearing: the
chronology, the numbered points to argue, the provisions, the authorities, the
likely objections, the paper-book references and the prayer.

Two ways a sheet comes into being:
  • prepared by Headnote from the matter's own file (`source='junior'`), or
  • read from the sheet the advocate wrote by hand (`source='hand'`).

Either way nothing is invented: facts and dates trace to the file or the court
record, and anything the reader must check is flagged, not smoothed over.
"""

from headnote.notesheets import readiness, storage  # noqa: F401

__all__ = ["readiness", "storage"]
