"""Offline command-line audit for a Dossier v2 model and public readback.

The command only reads the explicitly supplied model and readback directory.  It
never discovers records, invokes Runtime, reads a database, or writes a
publication.  A readback directory is an operator-exported map of exact public
publication IDs to their immutable bytes; its files are named by SHA-256 ID.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

from .dossier import DossierReport
from .dossier_release import DossierReleaseGate, DossierReleasePackage

_COMMANDS: Final[tuple[str, ...]] = ("inspect", "verify", "rebuild")


class _DirectoryReadback:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def read_publication(self, publication_id: str) -> bytes:
        return (self.directory / publication_id).read_bytes()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manager-gui-dossier",
        description=(
            "Offline Dossier v2 inspect/verify/rebuild audit; "
            "never publishes or calls Runtime."
        ),
    )
    parser.add_argument("command", choices=_COMMANDS)
    parser.add_argument("--model", type=Path, required=True, help="canonical Dossier model JSON")
    parser.add_argument(
        "--readback-dir",
        type=Path,
        help="operator-exported exact public bytes, one file per SHA-256 publication ID",
    )
    parser.add_argument(
        "--baseline-ref",
        action="append",
        dest="baseline_refs",
        help="explicit baseline public record ID (repeat for every root)",
    )
    parser.add_argument(
        "--current-root-id",
        action="append",
        dest="current_root_ids",
        help="explicit current root public record ID (repeat for every root)",
    )
    parser.add_argument(
        "--old-publication-id",
        action="append",
        dest="old_publication_ids",
        help="explicit old publication ID (repeat for every publication)",
    )
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    return parser


def _read_model(path: Path) -> DossierReport:
    return DossierReport.from_json(path.read_text(encoding="utf-8"))


def _inspection_dict(result: object) -> dict[str, object]:
    inspection = getattr(result, "verification", result)
    html = inspection.html_verification
    html_inspection = html.inspection
    return {
        "passed": inspection.passed,
        "published": inspection.published,
        "source_publication_id": inspection.source_publication_id,
        "artifact_id": inspection.artifact_id,
        "source_bytes_identical": inspection.source_bytes_identical,
        "artifact_bytes_identical": inspection.artifact_bytes_identical,
        "archive_bytes_identical": inspection.archive_bytes_identical,
        "old_records_byte_identical": inspection.old_records_byte_identical,
        "old_publications_byte_identical": inspection.old_publications_byte_identical,
        "runtime_submission_calls": inspection.runtime_submission_calls,
        "zero_runtime_calls": inspection.zero_runtime_calls,
        "external_readback_verified": inspection.external_readback_verified,
        "holdout_state_verified": inspection.holdout_state_verified,
        "quarantine_exclusion_verified": inspection.quarantine_exclusion_verified,
        "html": {
            "passed": html.passed,
            "fact_count": html_inspection.fact_count,
            "self_contained": html_inspection.self_contained,
            "has_boundary_banner": html_inspection.has_boundary_banner,
            "has_accessible_table": html_inspection.has_accessible_table,
            "has_theme_toggle": html_inspection.has_theme_toggle,
            "has_filters": html_inspection.has_filters,
            "has_tabs": html_inspection.has_tabs,
            "has_tooltips": html_inspection.has_tooltips,
            "has_responsive_layout": html_inspection.has_responsive_layout,
        },
        "errors": list(inspection.errors),
    }


def _package_dict(package: DossierReleasePackage) -> dict[str, object]:
    return {
        "published": package.published,
        "source_publication_id": package.source_publication_id,
        "artifact_id": package.artifact_id,
        "archive_sha256": package.archive_sha256,
        "renderer_version": package.renderer_version,
        "model_bytes": len(package.model_bytes),
        "html_bytes": len(package.html_bytes),
        "archive_bytes": len(package.archive_bytes),
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        model = _read_model(args.model)
        gate = DossierReleaseGate()
        package = gate.release(model)
        reader = None if args.readback_dir is None else _DirectoryReadback(args.readback_dir)
        common = {
            "public_reader": reader,
            "baseline_refs": args.baseline_refs,
            "current_root_ids": args.current_root_ids,
            "old_publication_ids": args.old_publication_ids,
        }
        if args.command == "rebuild":
            result = gate.rebuild(model, **common)
            output = {
                "command": args.command,
                "package": _package_dict(result.package),
                "published": result.published,
                "runtime_submission_calls": result.runtime_submission_calls,
                "zero_runtime_calls": result.zero_runtime_calls,
                "deterministic": result.deterministic,
                "old_records_byte_identical": result.old_records_byte_identical,
                "old_publications_byte_identical": result.old_publications_byte_identical,
                "verification": _inspection_dict(result),
            }
        else:
            result = gate.inspect(package, model=model, **common)
            output = {
                "command": args.command,
                "package": _package_dict(package),
                "verification": _inspection_dict(result),
            }
        print(
            json.dumps(
                output, ensure_ascii=False, sort_keys=True, indent=2 if args.pretty else None
            )
        )
        return 0 if output["verification"]["passed"] else 1  # type: ignore[index]
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"command": args.command, "passed": False, "error": str(exc)},
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised through the console script
    sys.exit(main())
