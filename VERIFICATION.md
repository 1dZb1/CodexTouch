# Verification

Checked on Windows with Python 3.13 x64 and an MX Master 4 on 2026-11-11.

- The mouse reported its haptic capabilities and acknowledged the manual
  double-click, triple-click and wave-then-click examples.
- The test suite covers pattern limits, event routing, fail-open hook output,
  configuration preservation and installer removal.
- The installer was exercised through PowerShell with spaces, apostrophes,
  special characters and an emoji in the installation and configuration paths.
  The generated hook accepted a JSON event through standard input.

The public package has not yet been verified end-to-end in a fresh Codex
installation with its hooks reviewed and enabled. Device acknowledgment also
does not establish how a pattern feels. Other mouse transport modes, firmware
revisions and multiple matching devices remain untested.
