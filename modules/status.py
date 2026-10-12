"""Processor status reporting without importing the local GUI in headless runs."""

import modules.globals


def update_status(message: str, scope: str = 'DLC.CORE') -> None:
    if modules.globals.headless:
        print(f'[{scope}] {message}')
        return

    # Preserve the existing GUI status routing when run.py owns the process.
    from modules.core import update_status as update_local_status

    update_local_status(message, scope)
