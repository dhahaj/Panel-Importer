"""ODB++ reader, written against the ODB++ Design Format Specification (v7.0 and 8.1).

Everything is converted to millimetres on read.  Records the code does not recognise
are reported as issues, never silently skipped.
"""

from panelimport.io.odb.job import OdbJob, OdbOpenError

__all__ = ["OdbJob", "OdbOpenError"]
