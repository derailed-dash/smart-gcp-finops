#!/usr/bin/env python3
# /// script
# dependencies = [
#   "rich",
# ]
# ///
"""Dynamic Makefile target parser and formatter.

Reads the root Makefile, extracts target definitions and their preceding comments,
and renders a styled, two-column help menu using the Rich library.
"""

import re
import sys

from rich.console import Console
from rich.table import Table


def print_section(console: Console, title: str | None, targets: list[tuple[str, str]]) -> None:
    """Renders a section title and its targets in a borderless aligned table.

    Args:
        console: The Rich Console instance to print to.
        title: The name of the section (e.g. 'Installation & Setup').
        targets: A list of tuples containing (target_name, description).
    """
    if not targets:
        return
    if title:
        console.print(f"\n[bold yellow]{title}[/]")
        console.print(f"[yellow]{'-' * len(title)}[/]")

    # Configure a borderless table layout with column padding
    table = Table(
        box=None, show_header=False, show_edge=False, pad_edge=False, padding=(0, 2, 0, 0)
    )
    table.add_column("Target", style="bold green", width=24)
    table.add_column("Description", style="reset")

    for target, desc in targets:
        table.add_row(target, desc if desc else "[dim](No description)[/]")
    console.print(table)


def main() -> None:
    """Parses the Makefile and outputs the self-documenting help menu."""
    try:
        with open("Makefile") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print("Error: Makefile not found.", file=sys.stderr)
        sys.exit(1)

    console = Console()
    console.print("[bold]FinSavant Makefile Targets[/]")
    console.print("Usage: make [cyan]<target>[/]")

    current_comments = []
    current_section_title = None
    current_section_targets = []

    i = 0
    while i < len(lines):
        line_str = lines[i].strip()

        # State 1: Detect Section Headers of the form:
        # # ==========================================
        # # Section Name
        # # ==========================================
        if line_str.startswith("# =====") and i + 2 < len(lines):
            title_line = lines[i + 1].strip()
            divider_line = lines[i + 2].strip()
            if title_line.startswith("# ") and not title_line.startswith("# ==="):
                if divider_line.startswith("# ====="):
                    new_title = title_line.lstrip("#").strip()
                    # Print accumulated targets for the previous section before starting a new one
                    print_section(console, current_section_title, current_section_targets)
                    current_section_title = new_title
                    current_section_targets = []
                    current_comments = []
                    i += 3
                    continue

        # State 2: Accumulate comment blocks preceding target definitions
        if line_str.startswith("#"):
            comment = line_str.lstrip("#").strip()
            # Ignore divider comments, but include all others (like Notes and Warnings)
            if not comment.startswith("==="):
                current_comments.append(comment)
        # State 3: Empty lines reset accumulated comments
        elif not line_str:
            current_comments = []
        # State 4: Code/Target lines
        else:
            # Targets must start at column 1 (no leading whitespace).
            # This prevents recipe command lines from matching as targets.
            if not lines[i][0].isspace():
                # Matches valid target names (alphanumeric/hyphen/underscore) followed by a colon
                # Negative lookahead (?!==) excludes variable assignments like ':='
                match = re.match(r"^([a-zA-Z0-9_-]+)\s*:(?!=)", line_str)
                if match:
                    target = match.group(1)
                    # Ignore the help target itself to avoid recursion confusion
                    if target != "help":
                        desc_text = "\n".join(current_comments)
                        current_section_targets.append((target, desc_text))
            # Any non-comment, non-empty code line clears accumulated comments
            current_comments = []
        i += 1

    # Print the final remaining section
    print_section(console, current_section_title, current_section_targets)


if __name__ == "__main__":
    main()
