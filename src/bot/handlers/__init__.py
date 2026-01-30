"""
Bot handlers package.

Contains all command, message, and callback handlers.
Each handler module exports its own router that gets registered to the main dispatcher.
"""

from . import start, analyze, commands, callbacks, export

# Export routers for registration
__all__ = ['start', 'analyze', 'commands', 'callbacks', 'export']
