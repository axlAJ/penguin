"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, searchterms
from .checks import DEFAULT_REQUIRED_FIELDS, run_all
from .loadfile import LoadFileError, read_dat, read_opt
from .report import write_csv, write_html


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="penguin",
        description="Check an eDiscovery production before it ships.",
    )
    parser.add_argument("--version", action="version", version=f"Penguin {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run every check against a production volume")
    run.add_argument("--dat", required=True, help="Concordance DAT metadata file")
    run.add_argument("--opt", help="Opticon image load file")
    run.add_argument("--volume", default=".", help="root directory of the volume")
    run.add_argument("--terms", help="search term list, one per line")
    run.add_argument("--html", help="write an HTML report here")
    run.add_argument("--csv", help="write the exception log here")
    run.add_argument("--encoding", default="utf-8-sig", help="load file encoding")
    run.add_argument(
        "--require",
        nargs="*",
        default=None,
        help=f"required columns (default: {' '.join(DEFAULT_REQUIRED_FIELDS)})",
    )
    run.add_argument(
        "--fail-on",
        choices=["blocker", "any", "never"],
        default="blocker",
        help="what makes the command exit non-zero",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.volume)

    try:
        dat = read_dat(args.dat, encoding=args.encoding)
        opt = read_opt(args.opt, encoding=args.encoding) if args.opt else None
    except (LoadFileError, OSError) as exc:
        print(f"penguin: {exc}", file=sys.stderr)
        return 2

    findings, summary = run_all(dat, opt, root, args.require)

    hits = []
    if args.terms:
        hits = searchterms.run(dat, root, searchterms.load_terms(args.terms))

    blockers = sum(1 for f in findings if f.is_blocker)
    warnings = len(findings) - blockers

    print(f"Records        {summary.records:,}")
    print(f"Bates          {summary.bates_first or '-'} to {summary.bates_last or '-'}")
    print(f"Pages          {summary.opt_pages:,}")
    print(f"Natives        {summary.natives_found:,} of {summary.natives_expected:,} present")
    print(f"Text           {summary.text_found:,} of {summary.text_expected:,} present")
    print(f"Blocking       {blockers}")
    print(f"To review      {warnings}")

    if findings:
        print()
        for finding in sorted(findings, key=lambda f: (not f.is_blocker, f.rule, f.record))[:15]:
            print(f"  [{finding.severity:<7}] {finding.rule:<20} {finding.record:<18} {finding.detail}")
        if len(findings) > 15:
            print(f"  ... {len(findings) - 15} more")

    if args.csv:
        write_csv(findings, args.csv)
        print(f"\nException log  {args.csv}")
    if args.html:
        write_html(findings, summary, hits, args.html, volume=Path(args.dat).stem)
        print(f"HTML report    {args.html}")

    if args.fail_on == "never":
        return 0
    if args.fail_on == "any":
        return 1 if findings else 0
    return 1 if blockers else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
