from __future__ import annotations

import base64
import binascii
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .models import (
    Availability,
    Derivation,
    ManagerReadModel,
    ReadModelError,
    ReadModelStatus,
    SourceReference,
)

_CHAPTER_BY_SCHEMA = {
    "apex-research.study-registration.v1": "intent",
    "apex-research.study-status-event.v1": "events",
    "apex-research.study-runtime-facts.v1": "attempts",
    "apex-research.sample-exposure.v1": "evidence",
    "apex-research.evidence.v1": "evidence",
    "apex-research.evidence.v2": "evidence",
    "apex-research.research-conclusion.v1": "conclusions",
}
_REPORT_SCHEMAS = frozenset(
    {
        "apex-research.study-report-source.v1",
        "apex-research.study-report-source.v2",
        "apex-research.strategy-report-source.v2",
        "apex-research.campaign-report-source.v1",
        "apex-research.replication-report-source.v1",
        "apex-research.cpa-factor-report-source.v1",
        "strategy-reporting.report-descriptor.v1",
        "strategy-reporting.report-envelope.v1",
    }
)

_VIEW_RESOURCES = (
    "atlas",
    "stories",
    "genomes",
    "genome_conditions",
    "genome_comparison",
    "memory",
    "failure_patterns",
    "evidence",
    "lineage",
    "evidence_comparison",
    "failure_grouping",
    "methodology",
    "history",
    "source_documents",
    "search",
    "report_source",
)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    ).hexdigest()


def workspace_launch_guidance(root: str, port: int) -> str:
    # This command is for PowerShell; single quotes prevent user paths becoming shell code.
    quoted_root = "'" + root.replace("'", "''") + "'"
    return (
        "从 QuantResearch 检出目录（包含 manager-gui 和 strategy-workspace 克隆）执行：\n"
        "uv run --no-project --isolated --refresh-package quantresearch-manager-gui "
        '--refresh-package strategy-workspace --with "./manager-gui[workspace]" '
        '--with "./strategy-workspace" python -I -m manager_gui.web '
        f"--provider workspace --workspace-root {quoted_root} --port {port}\n"
        "已安装的 site-packages 不是源码安装路径。"
        "不要在运行实例的 venv 目录里跑会重建 venv 的 uv 命令。"
    )


class WorkspaceDataProvider:
    def __init__(self, root: str | Path, *, limit: int = 100) -> None:
        from strategy_workspace import WorkspaceClient, WorkspaceError

        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        self._client = WorkspaceClient(Path(root), read_only=True)
        self._input = {
            "runs": self._client.list_runs(limit=limit),
            "records": self._client.list_records(limit=limit),
        }
        self._scope = {
            "application_read_view": {
                "kind": "application-frozen-public-input",
                "workspace": "workspace-" + _digest(str(Path(root).resolve())),
                "resources": list(_VIEW_RESOURCES),
                "lifetime": "provider instance; unavailable after replacement",
                "observation_time": "not supplied by public reads",
                "owner_transport_bytes": False,
            },
            "list_limit": limit,
            "runs_observed": len(self._input["runs"]),
            "publications_observed": len(self._input["records"]),
            "global_catalog": False,
            "cross_resource_atomic_snapshot": False,
            "lineage_root_limit": 10,
            "lineage_depth": 1,
            "lineage_page_size": 100,
            "artifact_byte_limit": 2_000_000,
            "runs_limit_reached": len(self._input["runs"]) == limit,
            "publications_limit_reached": len(self._input["records"]) == limit,
        }
        self._errors = []
        self._relations = []
        self._scope["lineage_pages"] = []
        self._input["lineage_pages"] = []
        self._input["packages"] = []
        package_refs = []
        for run in self._input["runs"]:
            ref = (run.get("request") or {}).get("strategy_package")
            if ref is None or ref in package_refs:
                continue
            package_refs.append(ref)
            try:
                package = self._client.get_registered_package(ref)
                if package["package_ref"] != ref:
                    raise ValueError("Package readback differs from the published run reference")
                self._input["packages"].append(package)
            except WorkspaceError as exc:
                self._errors.append(ReadModelError(exc.code, str(exc), run["run_id"]))

        self._lineage_error = None
        roots = [record for record in self._input["records"] if record.get("lineage")]
        self._scope["lineage_roots_available"] = len(roots)
        owner_snapshot = None
        for record in roots[:10]:
            query = {
                "roots": [{"kind": "publication", "id": record["record_id"]}],
                "direction": "ancestors",
                "max_depth": 1,
                "page_size": 100,
                "relations": [],
                "record_types": [],
                "snapshot_token": owner_snapshot,
            }
            try:
                page = self._client.query_lineage(**query)
            except WorkspaceError as exc:
                self._lineage_error = ReadModelError(exc.code, str(exc), record["record_id"])
                self._errors.append(self._lineage_error)
                continue
            owner_snapshot = page["snapshot_token"]
            self._input["lineage_pages"].append(page)
            self._scope["lineage_pages"].append(
                {**query, **{key: page[key] for key in ("snapshot_token", "next_cursor")}}
            )
            for connected in page["records"]:
                existing = next(
                    (
                        item
                        for item in self._input["records"]
                        if item["record_id"] == connected["record_id"]
                    ),
                    None,
                )
                if existing is None:
                    self._input["records"].append(connected)
                elif existing != connected:
                    raise ValueError("Public record changed during read-view acquisition")
        for record in self._input["records"]:
            for edge in record.get("lineage", []):
                self._relations.append(
                    {
                        **edge,
                        "source": edge["source_id"],
                        "target": record["record_id"],
                        "source_refs": [record["record_id"]],
                    }
                )
        self._sources = []
        self._input["artifact_reads"] = {}
        refs = [ref for record in self._input["records"] for ref in record.get("artifacts", [])]
        for run in self._input["runs"]:
            result = run.get("result") or {}
            refs.extend(result.get("artifacts", []))
            if result.get("schema") in {
                "quant-research.result.v2",
                "quant-research.result.v3",
                "quant-research.result.v4",
            }:
                parts = [result.get("discovery") or {}, *(result.get("formal") or {}).values()]
                refs.extend(ref for part in parts for ref in part.get("artifacts", []))
        for ref in refs:
            identifier = ref.get("sha256")
            if not isinstance(identifier, str):
                self._errors.append(ReadModelError("invalid_artifact_ref", "No published digest."))
                continue
            existing_source = next(
                (source for source in self._sources if source["artifact_id"] == identifier),
                None,
            )
            if existing_source is not None:
                if any(
                    existing_source["raw_source"].get(key) != ref.get(key)
                    for key in ("uri", "sha256", "bytes", "media_type")
                ):
                    existing_source["read_status"] = "integrity_failure"
                    existing_source.pop("text", None)
                    existing_source["reason"] = "Published artifact references conflict."
                    self._errors.append(
                        ReadModelError(
                            "artifact_ref_conflict",
                            existing_source["reason"],
                            identifier,
                        )
                    )
                continue
            source = {
                "artifact_id": identifier,
                "source_id": identifier,
                "title": ref.get("name"),
                "locator": ref.get("uri"),
                "raw_source": ref,
                "source_revision": identifier,
                "read_status": "api_unavailable",
            }
            self._sources.append(source)
            try:
                if (
                    len(identifier) != 64
                    or any(c not in "0123456789abcdef" for c in identifier)
                    or ref.get("uri") != "workspace-artifact://sha256/" + identifier
                ):
                    raise ValueError("Invalid published artifact identity")
                if type(ref.get("bytes")) is not int or not 0 <= ref["bytes"] <= 2_000_000:
                    source["reason"] = (
                        "Artifact size unavailable or exceeds 2000000-byte read limit."
                    )
                    self._errors.append(
                        ReadModelError(
                            "artifact_read_limit",
                            source["reason"],
                            identifier,
                        )
                    )
                    continue
                readback = self._client.read_artifact(ref["uri"])
                self._input["artifact_reads"][identifier] = readback
                descriptor = readback["artifact"]
                if any(
                    descriptor.get(key) != ref.get(key)
                    for key in ("uri", "sha256", "bytes", "media_type")
                ):
                    raise ValueError("Artifact readback identity differs from published reference")
                if readback["encoding"] != "base64":
                    raise ValueError("Unsupported artifact encoding")
                content = base64.b64decode(readback["content"], validate=True)
                if (
                    len(content) != ref["bytes"]
                    or hashlib.sha256(content).hexdigest() != identifier
                ):
                    raise ValueError("Artifact bytes differ from published digest or length")
                source["read_status"] = "known"
                media_type = ref.get("media_type", "").split(";", 1)[0]
                if media_type.startswith("text/") or media_type == "application/json":
                    try:
                        source["text"] = content.decode("utf-8")
                    except UnicodeError:
                        source["read_status"] = "api_unavailable"
                        source["reason"] = "Published bytes are not UTF-8 readable text."
                else:
                    source["reason"] = "Published bytes are not a supported text document."
            except WorkspaceError as exc:
                source["read_status"] = (
                    "integrity_failure" if "integrity" in exc.code else "api_unavailable"
                )
                source["reason"] = str(exc)
                self._errors.append(ReadModelError(exc.code, str(exc), identifier))
            except (ValueError, KeyError, TypeError, binascii.Error) as exc:
                source["read_status"] = "integrity_failure"
                source["reason"] = str(exc)
                self._errors.append(
                    ReadModelError("artifact_integrity_failed", str(exc), identifier)
                )
        self._token = "workspace-view-" + _digest(
            {
                "root": str(Path(root).resolve()),
                "input": self._input,
                "scope": self._scope,
                "sources": self._sources,
                "errors": [error.to_dict() for error in self._errors],
            }
        )
        self._records = []
        self._refs = []
        self._chapters = {chapter: [] for chapter in set(_CHAPTER_BY_SCHEMA.values())}
        self._chapters["attempts"] = []
        self._reports = []
        self._documents = []
        self._events = []
        self._results = []
        for source in self._sources:
            source["snapshot_token"] = self._token
            self._refs.append(
                SourceReference(
                    source["source_id"],
                    "strategy-workspace",
                    "artifact",
                    source.get("locator") or f"workspace://artifact/{source['artifact_id']}",
                    revision=source["artifact_id"],
                )
            )
        for run in self._input["runs"]:
            identifier = run["run_id"]
            item = {
                "record_id": identifier,
                "record_type": "run",
                "title": identifier,
                "state": run["status"],
                "execution_status": run["status"],
                "source_ref": identifier,
                "source_revision": _digest(run),
                "snapshot_token": self._token,
                "raw_source": run,
            }
            if run.get("result") is not None:
                self._results.append(
                    {
                        "record_id": identifier,
                        "record_type": "run_result",
                        "schema": run["result"].get("schema"),
                        "title": identifier,
                        "source_ref": identifier,
                        "source_revision": _digest(run),
                        "snapshot_token": self._token,
                        "raw_source": run["result"],
                    }
                )
            self._records.append(item)
            self._chapters["attempts"].append(
                {key: value for key, value in item.items() if key != "state"}
            )
            self._refs.append(
                SourceReference(
                    identifier,
                    "strategy-workspace",
                    "run",
                    f"workspace://run/{identifier}",
                    schema=run.get("schema"),
                    revision=_digest(run),
                )
            )
        for publication in self._input["records"]:
            identifier = publication["record_id"]
            payload = publication["payload"]
            schema = publication["record_type"]
            supported = (schema in _CHAPTER_BY_SCHEMA or schema in _REPORT_SCHEMAS) and payload.get(
                "schema"
            ) == schema
            item = {
                "record_id": identifier,
                "record_type": schema,
                "schema": payload.get("schema"),
                "title": payload.get("title") or identifier,
                "source_ref": identifier,
                "source_revision": _digest(publication),
                "snapshot_token": self._token,
                "raw_source": publication,
                "mapping_supported": supported,
            }
            artifacts = publication.get("artifacts", [])
            if len(artifacts) == 1 and isinstance(artifacts[0].get("sha256"), str):
                item["original_source_id"] = artifacts[0]["sha256"]
                item["original_snapshot_token"] = self._token
                item["original_source_revision"] = artifacts[0]["sha256"]
            if supported:
                for key in (
                    "summary",
                    "description",
                    "body",
                    "reason",
                    "limitations",
                    "decision",
                    "evidence_level",
                    "author",
                    "scope",
                    "period",
                    "version",
                    "sections",
                    "registration",
                    "research",
                    "study_id",
                    "strategy_family",
                    "run_id",
                    "evidence",
                    "unresolved_explanations",
                    "next_actions",
                    "clauses",
                    "findings",
                    "data_roles",
                    "real_constraints",
                    "method_protocol",
                    "sources",
                    "source_record_ids",
                    "workspace_run_ids",
                    "protocol",
                    "trials",
                    "gate_results",
                    "research_metrics",
                    "report_kind",
                    "subject_id",
                    "payload_schema",
                    "renderer_version",
                    "identity",
                ):
                    if key in payload:
                        item[key] = deepcopy(payload[key])
                if isinstance(payload.get("body"), str):
                    item["summary"] = payload["body"]
                elif isinstance(payload.get("reason"), str):
                    item["summary"] = payload["reason"]
                if schema == "apex-research.study-status-event.v1":
                    if "status" in payload:
                        item["study_status"] = payload["status"]
                    item["source_event_time"] = publication.get("created_at")
                chapter = _CHAPTER_BY_SCHEMA.get(schema)
                if chapter is not None:
                    self._chapters[chapter].append(item)
                if schema in _REPORT_SCHEMAS:
                    report = {
                        **item,
                        "report_id": payload.get("report_id") or identifier,
                        "source_publication": {
                            **item,
                            "publication_id": identifier,
                            "published_at": publication.get("created_at"),
                        },
                    }
                    self._reports.append(report)
                    self._documents.append(
                        {
                            **item,
                            "document_id": identifier,
                            "document_type": "report",
                            "source_locator": f"workspace://record/{identifier}",
                            "updated_at": publication.get("created_at"),
                        }
                    )
            else:
                self._errors.append(
                    ReadModelError(
                        "unsupported_record_type",
                        "Record meaning is not mapped; raw identity retained.",
                        identifier,
                        details={"record_type": schema, "schema": payload.get("schema")},
                    )
                )
            self._records.append(item)
            if publication.get("created_at"):
                self._events.append(
                    {
                        **item,
                        "event_type": "publication",
                        "source_event_time": publication["created_at"],
                    }
                )
            self._refs.append(
                SourceReference(
                    identifier,
                    "strategy-workspace",
                    "publication",
                    f"workspace://record/{identifier}",
                    schema=publication["record_type"],
                    revision=_digest(publication),
                )
            )

        for source in self._sources:
            self._documents.append(
                {
                    "document_id": "artifact-document-" + source["artifact_id"],
                    "document_type": "raw-evidence",
                    "title": source.get("title") or source["artifact_id"],
                    "source_ref": source["source_id"],
                    "source_revision": source["source_revision"],
                    "snapshot_token": self._token,
                    "source_locator": source.get("locator"),
                    "original_source_id": source["source_id"],
                    "original_snapshot_token": self._token,
                    "original_source_revision": source["source_revision"],
                    "read_status": source["read_status"],
                    "raw_source": source["raw_source"],
                }
            )

    def read(
        self, resource: str = "atlas", *, snapshot_token: str | None = None
    ) -> ManagerReadModel:
        if snapshot_token is not None and snapshot_token != self._token:
            return ManagerReadModel(
                {},
                (),
                None,
                snapshot_token if snapshot_token.strip() else None,
                Derivation("direct"),
                Availability(ReadModelStatus.STALE, False, "Unknown application read-view token."),
                (ReadModelError("snapshot_drift", "The requested read view is unavailable."),),
            )
        if resource not in {
            "atlas",
            "stories",
            "evidence",
            "lineage",
            "history",
            "source_documents",
            "search",
            "report_source",
        }:
            reason = (
                "The approved Workspace reads do not provide this resource's catalog or "
                "semantic mapping; absence is not confirmed. Package detail is not a Genome "
                "or methodology. get_genome, inspect_package, validate_parameters, "
                "verify_artifact and doctor are not approved."
            )
            return ManagerReadModel(
                {},
                (),
                None,
                self._token,
                Derivation("direct"),
                Availability(ReadModelStatus.API_UNAVAILABLE, False, reason),
                (
                    ReadModelError(
                        "api_unavailable",
                        reason,
                        details=deepcopy({"coverage": {**self._scope, "resource": resource}}),
                    ),
                ),
            )
        content = {
            "atlas": {"records": self._records},
            "stories": self._chapters,
            "evidence": {
                "records": self._results
                + [
                    item
                    for chapter in ("evidence", "conclusions")
                    for item in self._chapters[chapter]
                ]
            },
            "history": {"events": self._events},
            "source_documents": {"documents": self._documents},
            "report_source": {"reports": self._reports},
            "search": {"records": self._records, "pagination": {"complete": False}},
            "lineage": {
                "schema": "manager-gui.lineage.v1",
                "nodes": [],
                "edges": [],
                "relations": self._relations,
                "pagination": {
                    "complete": False,
                    "has_more": any(page["next_cursor"] for page in self._input["lineage_pages"]),
                },
            },
        }[resource]
        return ManagerReadModel(
            data=deepcopy(
                {
                    **content,
                    "sources": self._sources,
                    "public_input": self._input,
                    "coverage": {**self._scope, "resource": resource},
                }
            ),
            source_refs=tuple(self._refs),
            as_of=None,
            snapshot_token=self._token,
            derivation=Derivation("direct"),
            availability=Availability(
                ReadModelStatus.API_UNAVAILABLE
                if resource == "lineage" and self._lineage_error
                else ReadModelStatus.KNOWN,
                False,
                f"Bounded public reads: list limit {self._scope['list_limit']}; "
                f"{self._scope['runs_observed']} runs and "
                f"{self._scope['publications_observed']} listed publications. "
                "Lineage: at most 10 public roots, ancestors, depth 1, first 100-record page "
                "per root; no relation/type filter. Artifact reads: at most 2000000 bytes each. "
                "Application-frozen input, not a global catalog or an atomic owner snapshot.",
            ),
            errors=deepcopy(tuple(self._errors)),
        )
