# summary: "Exports the DSPx server application factory and command entry point."
# read_when:
#   - "Changing public imports exposed by the dspx.server package."

from .app import create_app, main

__all__ = ["create_app", "main"]
