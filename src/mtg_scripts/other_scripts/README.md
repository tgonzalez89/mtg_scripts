Contains small utilities for counting lines, filtering lists, ranking vanilla creatures, and creating MTG tables.

Each tool exposes `main(argv=None) -> int`; imports do not execute the tools. Expected file/service failures return 1;
argparse still handles help and invalid arguments with status 0 and 2. Text counting/filtering and document formats are unchanged.

`vanilla` now writes `vanilla_creatures.txt` to the working directory by default rather than beside the installed script.
Use `--output PATH` to select a different location. Arbitrary queries and ranking/output formatting are unchanged;
results now use the shared Scryfall cache and the service follows all pages, so queries previously truncated after one
or more pages can return additional cards.
