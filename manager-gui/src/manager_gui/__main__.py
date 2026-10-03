"""Command-line entry point for the fixture-backed Manager GUI contract."""

from __future__ import annotations

import argparse
import sys

from .fixtures import FIXTURE_STATES, fixture_provider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manager-gui",
        description="Read a ManagerReadModel v0 fixture; no owner state is mutated.",
    )
    parser.add_argument(
        "--fixture",
        choices=FIXTURE_STATES,
        default="empty",
        help="fixture availability state (default: empty)",
    )
    parser.add_argument("--resource", default="atlas", help="opaque read resource name")
    parser.add_argument(
        "--snapshot-token",
        default=None,
        help="optional opaque snapshot token carried to the fixture provider",
    )
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    model = fixture_provider(args.fixture).read(
        args.resource,
        snapshot_token=args.snapshot_token,
    )
    print(model.to_json(indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the console script
    sys.exit(main())
