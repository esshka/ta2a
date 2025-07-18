"""
Utility functions module.

Common utility functions for time handling, validation, and other
shared functionality across the system.

Time Semantics:
- Market timestamps from data feeds are ALWAYS authoritative
- Wall-clock time is only used for operational purposes and fallback
- All signal timestamps should use market time for consistency
- Latency monitoring tracks difference between market and wall-clock time
"""
