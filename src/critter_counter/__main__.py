"""Command-line entry point: ``python -m critter_counter [options]``.

Also installed as the ``critter-counter`` command. Run with ``--help`` for
the options.
"""

from .app import CritterCounterApp
from .settings import Settings


def main(argv=None):
    """Parse options and run the app until Ctrl-C.

    Args:
        argv: Argument list without the program name; defaults to
            ``sys.argv[1:]``.
    """
    CritterCounterApp(Settings.from_args(argv)).start()


if __name__ == "__main__":
    main()
