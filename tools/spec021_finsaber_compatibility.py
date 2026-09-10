"""Replay the bounded FINSABER v2.0.1 adoption spike in an isolated upstream env."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

HARNESS_PATH = Path(__file__).with_name("installed_wheel_harness.py")
HARNESS_SPEC = importlib.util.spec_from_file_location(
    "installed_wheel_harness", HARNESS_PATH
)
assert HARNESS_SPEC is not None and HARNESS_SPEC.loader is not None
HARNESS = importlib.util.module_from_spec(HARNESS_SPEC)
HARNESS_SPEC.loader.exec_module(HARNESS)

EXPECTED_WHEEL_SHA256 = (
    "ed2d1dcad2785daa1a89ab4bfc089f71d685e7fa7148466d3fdbba6f6fe96140"
)
EXPECTED_SEMANTIC_SHA256 = (
    "8e6e0e63170b9cb0b5d8641661dfa8ef33413c8f4c2dda079c842eddde3341ae"
)
EXPECTED_EDGE = {
    "margin_executed": 100,
    "board_lot_executed": 150,
    "tick_fill": 100.003,
}
NODE_TIMEOUT_SECONDS = 30
RESULT_PREFIX = "SPEC021_RESULT="

PROBE_SOURCE = r'''from __future__ import annotations

import hashlib
import importlib.metadata
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from finsaber import FINSABER, FinsaberDataset
from finsaber.strategy.timing_llm import BaseStrategyIso
from finsaber.toolkit.result_writer import write_result_artifacts


class BuyAtIndex(BaseStrategyIso):
    def __init__(self, symbol: str, index: int, quantity: int):
        super().__init__()
        self.symbol = symbol
        self.index = index
        self.quantity = quantity
        self.seen = 0
        self.disable_logger()

    def on_data(self, current_date, today_data, framework):
        if self.seen == self.index:
            framework.buy(current_date, self.symbol, price=999.0, quantity=self.quantity)
        self.seen += 1


def loader(*, constant: bool = False, close: float | None = None):
    symbol = "AAPL.XNAS"
    sessions = [value.date() for value in pd.bdate_range("2024-01-02", periods=22)]
    data: dict[date, dict[str, object]] = {}
    for offset, session in enumerate(sessions):
        open_price = 100.0 if constant else 100.0 + offset
        close_price = close if close is not None else open_price + 0.5
        data[session] = {
            "price": {
                symbol: {
                    "open": open_price,
                    "high": max(open_price, close_price),
                    "low": min(open_price, close_price),
                    "close": close_price,
                    "adjusted_close": close_price,
                    "volume": 1000,
                }
            }
        }
    return symbol, sessions, FinsaberDataset(data=data)


def execute(*, cash=10000.0, index=0, quantity=10, costs=None, constant=False, close=None):
    costs = costs or {}
    symbol, sessions, data = loader(constant=constant, close=close)
    config = {
        "data_loader": data,
        "tickers": [symbol],
        "date_from": sessions[0].isoformat(),
        "date_to": sessions[-1].isoformat(),
        "cash": cash,
        "execution_timing": costs.get("execution_timing", "next_open"),
        "commission_per_share": costs.get("commission_per_share", 0.0),
        "min_commission": costs.get("min_commission", 0.0),
        "max_commission_rate": costs.get("max_commission_rate", 0.0),
        "slippage_perc": costs.get("slippage_perc", 0.0),
        "slippage_impact": costs.get("slippage_impact", 0.0),
        "liquidity_lookback_days": costs.get("liquidity_lookback_days", 5),
        "liquidity_min_history_days": costs.get("liquidity_min_history_days", 1),
        "liquidity_cap_pct": costs.get("liquidity_cap_pct", 0.0),
        "save_results": False,
        "silence": True,
        "setup_name": "spec021_probe",
    }
    leaf = FINSABER(config).run_iterative_tickers(
        BuyAtIndex,
        strat_params={"symbol": "$symbol", "index": index, "quantity": quantity},
    )[symbol]
    return symbol, sessions, leaf


def normalized(leaf):
    return {
        "trades": [
            {
                "signal_date": row.signal_date.isoformat(),
                "execution_date": row.execution_date.isoformat(),
                "side": row.type,
                "price": row.price,
                "quantity": int(row.quantity),
                "commission": row.commission,
                "slippage_cost": row.slippage_cost,
            }
            for row in leaf["trades"].itertuples(index=False)
        ],
        "equity": [
            {"date": row.datetime.isoformat(), "equity": row.equity}
            for row in leaf["equity_with_time"].itertuples(index=False)
        ],
        "metrics": {
            key: leaf[key]
            for key in (
                "final_value", "total_return", "annual_return", "annual_volatility",
                "sharpe_ratio", "sortino_ratio", "max_drawdown", "total_commission",
                "total_slippage", "total_trading_cost",
            )
        },
        "rejected_orders": leaf["rejected_orders"].to_dict(orient="records"),
    }


def provenance():
    dist = importlib.metadata.distribution("finsaber")
    return {
        "version": dist.version,
        "site_packages": str(Path(dist.locate_file(".")).resolve()),
        "direct_url": json.loads(dist.read_text("direct_url.json") or "{}"),
    }


def semantic():
    _symbol, _sessions, leaf = execute()
    return normalized(leaf)


def artifacts(output: Path):
    symbol, sessions, leaf = execute()
    semantic_result = normalized(leaf)
    window = f"{sessions[0].isoformat()}_{sessions[-1].isoformat()}"
    write_result_artifacts(
        output,
        {
            "schema": "spec021.fixture-config.v1",
            "tickers": [symbol],
            "execution_timing": "next_open",
            "snapshot_ref": "fixture://spec-021/equity-daily-v1",
        },
        {window: {symbol: leaf}},
    )
    manifest = output / "run_manifest.json"
    config = json.loads((output / "run_config.json").read_text(encoding="utf-8"))
    return {
        "semantic": semantic_result,
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "manifest": json.loads(manifest.read_text(encoding="utf-8")),
        "config": config,
        "files": sorted(path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()),
    }


def incompatible_edge():
    _symbol, _sessions, margin_leaf = execute(
        cash=10000.0, quantity=200, constant=True, close=100.0
    )
    _symbol, _sessions, lot_leaf = execute(
        cash=1000000.0, quantity=150, constant=True, close=100.0
    )
    _symbol, _sessions, tick_leaf = execute(
        cash=1000000.0,
        quantity=100,
        costs={"execution_timing": "same_close"},
        constant=True,
        close=100.003,
    )
    return {
        "margin_executed": int(margin_leaf["trades"].iloc[0]["quantity"]),
        "board_lot_executed": int(lot_leaf["trades"].iloc[0]["quantity"]),
        "tick_fill": float(tick_leaf["trades"].iloc[0]["price"]),
    }


def custom_log_base(output: Path):
    symbol, sessions, data = loader()
    config = {
        "data_loader": data,
        "tickers": [symbol],
        "date_from": sessions[0].isoformat(),
        "date_to": sessions[-1].isoformat(),
        "cash": 10000.0,
        "commission_per_share": 0.0,
        "min_commission": 0.0,
        "max_commission_rate": 0.0,
        "execution_timing": "next_open",
        "save_results": True,
        "silence": True,
        "setup_name": "spec021_custom_log",
        "log_base_dir": str(output),
    }
    error = None
    try:
        FINSABER(config).run_iterative_tickers(
            BuyAtIndex,
            strat_params={"symbol": "$symbol", "index": 0, "quantity": 10},
        )
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    return {
        "error": error,
        "files_written_before_error": sorted(
            path.relative_to(output).as_posix()
            for path in output.rglob("*")
            if path.is_file()
        ),
    }


mode = sys.argv[1]
argument = Path(sys.argv[2]) if len(sys.argv) > 2 else None
if mode == "provenance":
    result = provenance()
elif mode == "semantic":
    result = semantic()
elif mode == "artifacts":
    assert argument is not None
    result = artifacts(argument)
elif mode == "edge":
    result = incompatible_edge()
elif mode == "custom-log":
    assert argument is not None
    result = custom_log_base(argument)
else:
    raise SystemExit(f"unknown mode: {mode}")
print("SPEC021_RESULT=" + json.dumps(result, allow_nan=False, sort_keys=True))
'''


class TracerFailure(RuntimeError):
    """The compatibility tracer failed closed."""


def _progress(message: str) -> None:
    print(f"SPEC021_PROGRESS {message}", file=os.sys.stderr, flush=True)


def _parse(output: str) -> dict[str, Any]:
    matches = [line.removeprefix(RESULT_PREFIX) for line in output.splitlines() if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1:
        raise TracerFailure("upstream probe result framing is invalid")
    value = json.loads(matches[0])
    if not isinstance(value, dict):
        raise TracerFailure("upstream probe result must be an object")
    return value


def _run_node(
    python: Path,
    probe: Path,
    mode: str,
    environment: dict[str, str],
    argument: Path | None = None,
) -> dict[str, Any]:
    command = [str(python), "-I", "-B", str(probe), mode]
    if argument is not None:
        command.append(str(argument))
    _progress(f"node={mode} start timeout={NODE_TIMEOUT_SECONDS}")
    output = HARNESS.run_command(
        command,
        cwd=probe.parent,
        environment=environment,
        timeout_seconds=NODE_TIMEOUT_SECONDS,
    )
    _progress(f"node={mode} passed")
    return _parse(output)


def _verify_installed_wheel(python: Path, wheel: Path, provenance: dict[str, Any]) -> int:
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != EXPECTED_WHEEL_SHA256:
        raise TracerFailure("FINSABER wheel digest does not match v2.0.1")
    if provenance.get("version") != "2.0.1":
        raise TracerFailure("installed FINSABER version is not 2.0.1")
    direct_url = provenance.get("direct_url")
    if not isinstance(direct_url, dict) or not str(direct_url.get("url", "")).endswith(
        wheel.name
    ):
        raise TracerFailure("installed FINSABER was not sourced from the supplied wheel")
    site_packages = Path(str(provenance["site_packages"]))
    if python.parent.parent != site_packages.parent.parent:
        raise TracerFailure("upstream python and installed distribution are not one environment")
    verified = 0
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.endswith("/") or ".dist-info/" in name:
                continue
            installed = site_packages / Path(name)
            if not installed.is_file() or installed.read_bytes() != archive.read(name):
                raise TracerFailure(f"installed wheel file drifted: {name}")
            verified += 1
    if verified == 0:
        raise TracerFailure("wheel contains no verifiable package files")
    return verified


def run(upstream_python: Path, wheel: Path) -> dict[str, Any]:
    upstream_python = upstream_python.resolve()
    wheel = wheel.resolve()
    if not upstream_python.is_file() or not wheel.is_file():
        raise TracerFailure("upstream python and wheel must be files")
    environment = HARNESS.sanitized_environment()
    if "PYTHONPATH" in environment:
        raise TracerFailure("sanitized environment retained PYTHONPATH")
    with tempfile.TemporaryDirectory(prefix="spec021-finsaber-") as temporary:
        root = Path(temporary).resolve()
        probe = root / "probe.py"
        probe.write_text(PROBE_SOURCE, encoding="utf-8", newline="\n")
        provenance = _run_node(upstream_python, probe, "provenance", environment)
        verified_files = _verify_installed_wheel(
            upstream_python, wheel, provenance
        )
        semantic = _run_node(upstream_python, probe, "semantic", environment)
        edge = _run_node(upstream_python, probe, "edge", environment)
        if edge != EXPECTED_EDGE:
            raise TracerFailure("margin, lot, or tick incompatibility observation drifted")
        custom_log = _run_node(
            upstream_python, probe, "custom-log", environment, root / "custom-log"
        )
        if (
            not isinstance(custom_log.get("error"), dict)
            or custom_log["error"].get("type") != "FileNotFoundError"
            or len(custom_log.get("files_written_before_error", [])) != 9
        ):
            raise TracerFailure("custom output-root failure observation drifted")
        artifact_replays = [
            _run_node(
                upstream_python,
                probe,
                "artifacts",
                environment,
                root / f"artifacts-{replay}",
            )
            for replay in (1, 2)
        ]
        semantics = [item.pop("semantic") for item in artifact_replays]
        semantic_hashes = [
            hashlib.sha256(
                json.dumps(item, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            for item in semantics
        ]
        if (
            semantic != semantics[0]
            or semantic_hashes != [EXPECTED_SEMANTIC_SHA256] * 2
        ):
            raise TracerFailure("meaning-bearing FINSABER transcript drifted on replay")
        manifest_hashes = [item["manifest_sha256"] for item in artifact_replays]
        if manifest_hashes[0] == manifest_hashes[1]:
            raise TracerFailure("expected generated-at artifact drift was not observed")
        return {
            "ok": True,
            "wheel_sha256": EXPECTED_WHEEL_SHA256,
            "pythonpath": "cleared",
            "node_timeout_seconds": NODE_TIMEOUT_SECONDS,
            "nodes": [
                "provenance",
                "semantic",
                "edge",
                "custom-log",
                "artifacts",
                "artifacts",
            ],
            "replays": 2,
            "verified_installed_files": verified_files,
            "provenance": provenance,
            "semantic_sha256": semantic_hashes,
            "artifact_manifest_sha256": manifest_hashes,
            "artifact_generated_at_utc": [
                item["manifest"]["generated_at_utc"] for item in artifact_replays
            ],
            "artifact_files": artifact_replays[0]["files"],
            "edge": edge,
            "custom_log_base": custom_log,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-python", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        result = run(arguments.upstream_python, arguments.wheel)
    except (HARNESS.InstalledWheelFailure, OSError, TracerFailure, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=os.sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
