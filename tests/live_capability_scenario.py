#!/usr/bin/env python3
"""Live capability scenario for AbraFlexi MCP Server.

Exercises every MCP tool against a real AbraFlexi company and reports whether
each capability returns usable data (or correctly refuses writes under
READ_ONLY).

Usage:
  # Official public demo
  python tests/live_capability_scenario.py \\
    --url https://demo.flexibee.eu:5434 --company demo \\
    --login winstrom --password winstrom

  ABRAFLEXI_URL=https://flexibee-dev.spoje.net:5434 \\
  ABRAFLEXI_COMPANY=testa_invest_s_r_o_ \\
  ABRAFLEXI_LOGIN=admin ABRAFLEXI_PASSWORD=... READ_ONLY=true \\
    python tests/live_capability_scenario.py

Exit code is 0 only when every non-skipped check passes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class CheckResult:
    name: str
    kind: str  # tool | meta | guard
    ok: bool
    detail: str = ""
    sample: Any = None
    skipped: bool = False


@dataclass
class ScenarioReport:
    url: str
    company: str
    results: List[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        self.results.append(result)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.ok and not r.skipped)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok and not r.skipped)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.skipped)


def _parse_payload(data: Any) -> Any:
    if isinstance(data, str):
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data
    return data


def _is_error_payload(data: Any) -> Optional[str]:
    data = _parse_payload(data)
    if isinstance(data, str):
        low = data.lower()
        if "error" in low or "traceback" in low or "exception" in low:
            return data[:300]
        return None
    if not isinstance(data, dict):
        return None
    if data.get("error") is True or data.get("success") is False:
        return str(data.get("message") or data.get("reason") or data)[:300]
    # AbraFlexi envelope sometimes nests under winstrom
    w = data.get("winstrom")
    if isinstance(w, dict) and str(w.get("success")).lower() == "false":
        return str(w.get("message") or w)[:300]
    return None


def _has_usable_data(data: Any) -> Tuple[bool, str]:
    data = _parse_payload(data)
    err = _is_error_payload(data)
    if err:
        return False, err
    if data is None:
        return False, "null response"
    if isinstance(data, str):
        return (bool(data.strip()), "empty string" if not data.strip() else "ok string")
    if isinstance(data, list):
        return (True, f"list len={len(data)}")
    if isinstance(data, dict):
        if "records" in data:
            recs = data["records"]
            if recs is None:
                return False, "records=null"
            if isinstance(recs, list):
                return True, f"records={len(recs)}"
            return True, f"records type={type(recs).__name__}"
        if data.get("_context") or data.get("abraflexi_url") or data.get("company"):
            return True, "context/meta ok"
        if "success" in data:
            return True, f"success={data.get('success')}"
        if data:
            return True, f"keys={list(data.keys())[:8]}"
        return False, "empty object"
    return True, f"type={type(data).__name__}"


def _tool_is_readonly(tool: Any) -> bool:
    ann = getattr(tool, "annotations", None)
    if ann is None:
        return True
    if hasattr(ann, "read_only_hint"):
        return bool(ann.read_only_hint)
    if hasattr(ann, "readOnlyHint"):
        return bool(ann.readOnlyHint)
    if isinstance(ann, dict):
        return bool(ann.get("read_only_hint", ann.get("readOnlyHint", True)))
    return True


def _first_record_id(payload: Any) -> Optional[str]:
    data = _parse_payload(payload)
    if not isinstance(data, dict):
        return None
    recs = data.get("records")
    if isinstance(recs, list) and recs:
        first = recs[0]
        if isinstance(first, dict) and first.get("id") is not None:
            return str(first["id"])
    if isinstance(recs, dict):
        # sometimes evidence returns dict keyed by id
        for v in recs.values():
            if isinstance(v, dict) and v.get("id") is not None:
                return str(v["id"])
    return None


def _run_check(
    report: ScenarioReport,
    name: str,
    kind: str,
    fn: Callable[[], Any],
    *,
    require_data: bool = True,
    skip_reason: Optional[str] = None,
) -> Optional[Any]:
    if skip_reason:
        report.add(CheckResult(name=name, kind=kind, ok=True, detail=skip_reason, skipped=True))
        return None
    try:
        raw = fn()
        ok, detail = _has_usable_data(raw) if require_data else (True, "invoked")
        sample = _parse_payload(raw)
        # Keep a truncated *string* preview — never re-parse a sliced JSON blob
        try:
            preview = json.dumps(sample, ensure_ascii=False, default=str)
        except TypeError:
            preview = str(sample)
        report.add(
            CheckResult(
                name=name,
                kind=kind,
                ok=ok,
                detail=detail,
                sample=preview[:800],
            )
        )
        return raw
    except Exception as exc:  # noqa: BLE001 — scenario must keep going
        report.add(
            CheckResult(
                name=name,
                kind=kind,
                ok=False,
                detail=f"{type(exc).__name__}: {exc}",
                sample=traceback.format_exc()[-600:],
            )
        )
        return None


def run_scenario(
    url: str,
    company: str,
    login: str,
    password: str,
    *,
    read_only: bool = True,
) -> ScenarioReport:
    # Force env before importing/reloading the server module
    os.environ["ABRAFLEXI_URL"] = url
    os.environ["ABRAFLEXI_COMPANY"] = company
    os.environ["ABRAFLEXI_LOGIN"] = login
    os.environ["ABRAFLEXI_PASSWORD"] = password
    os.environ["READ_ONLY"] = "true" if read_only else "false"
    # Prevent .env from overriding CLI/env credentials
    os.environ.pop("ABRAFLEXI_AUTHSESSID", None)

    import importlib
    import abraflexi_mcp_server.server as server

    # Reset cached config and reload so env takes effect even on re-runs
    server.abraflexi_config = None
    server = importlib.reload(server)
    server.abraflexi_config = None

    report = ScenarioReport(url=url, company=company)
    tools = asyncio.run(server.mcp.list_tools())
    tool_by_name = {t.name: t for t in tools}
    fn_by_name = {
        name: getattr(server, name)
        for name in tool_by_name
        if callable(getattr(server, name, None))
    }

    report.add(
        CheckResult(
            name="tool_catalog",
            kind="meta",
            ok=len(tools) > 0,
            detail=f"{len(tools)} tools registered",
        )
    )

    # ---- core identity ----
    _run_check(report, "server_info", "tool", server.server_info)

    # ---- list/get tools that need no id ----
    inv = _run_check(
        report,
        "invoice_issued_get",
        "tool",
        lambda: server.invoice_issued_get(limit=5, detail="id"),
    )
    inv_id = _first_record_id(inv)

    rcv = _run_check(
        report,
        "invoice_received_get",
        "tool",
        lambda: server.invoice_received_get(limit=5, detail="id"),
    )
    rcv_id = _first_record_id(rcv)

    contact = _run_check(
        report,
        "contact_get",
        "tool",
        lambda: server.contact_get(limit=5, detail="id"),
    )
    contact_id = _first_record_id(contact)

    product = _run_check(
        report,
        "product_get",
        "tool",
        lambda: server.product_get(limit=5, detail="id"),
    )
    product_id = _first_record_id(product)

    bank = _run_check(
        report,
        "bank_transaction_get",
        "tool",
        lambda: server.bank_transaction_get(limit=5, detail="id"),
    )
    bank_id = _first_record_id(bank)

    ev_list = _run_check(report, "evidence_list", "tool", server.evidence_list)
    # evidence_list must come from the live evidence-list API (not a hardcoded 13)
    if ev_list is not None:
        parsed = _parse_payload(ev_list)
        count = None
        if isinstance(parsed, dict):
            count = parsed.get("count")
            if count is None and isinstance(parsed.get("evidences"), list):
                count = len(parsed["evidences"])
        elif isinstance(parsed, list):
            count = len(parsed)
        ok = isinstance(count, int) and count >= 50
        report.add(
            CheckResult(
                name="evidence_list:live_catalog_size",
                kind="meta",
                ok=ok,
                detail=f"count={count} (expect >=50 from evidence-list.json)",
            )
        )
    _run_check(
        report,
        "evidence_get:faktura-vydana",
        "tool",
        lambda: server.evidence_get(evidence="faktura-vydana", limit=3, detail="id"),
    )
    _run_check(
        report,
        "evidence_get_properties:faktura-vydana",
        "tool",
        lambda: server.evidence_get_properties(evidence="faktura-vydana"),
    )
    _run_check(
        report,
        "evidence_get_reports:faktura-vydana",
        "tool",
        lambda: server.evidence_get_reports(evidence="faktura-vydana"),
    )
    _run_check(
        report,
        "evidence_get_relations_list:faktura-vydana",
        "tool",
        lambda: server.evidence_get_relations_list(evidence="faktura-vydana"),
    )
    _run_check(
        report,
        "evidence_get_sum:faktura-vydana",
        "tool",
        lambda: server.evidence_get_sum(evidence="faktura-vydana"),
    )
    _run_check(report, "changes_status", "tool", server.changes_status)
    _run_check(
        report,
        "changes_get",
        "tool",
        lambda: server.changes_get(limit=5),
        require_data=True,
    )
    _run_check(
        report,
        "abraflexi_client_methods",
        "tool",
        lambda: server.abraflexi_client_methods(client_class="ReadOnly"),
    )
    _run_check(
        report,
        "invoice_issued_overdue_days",
        "tool",
        lambda: server.invoice_issued_overdue_days(due_date="2020-01-01"),
    )

    # ---- id-dependent read tools ----
    _run_check(
        report,
        "invoice_issued_get_email",
        "tool",
        lambda: server.invoice_issued_get_email(id=inv_id),
        skip_reason=None if inv_id else "no issued invoice id",
    )
    _run_check(
        report,
        "invoice_issued_get_recipients",
        "tool",
        lambda: server.invoice_issued_get_recipients(id=inv_id),
        skip_reason=None if inv_id else "no issued invoice id",
    )
    _run_check(
        report,
        "evidence_get_labels",
        "tool",
        lambda: server.evidence_get_labels(evidence="faktura-vydana", id=inv_id),
        skip_reason=None if inv_id else "no issued invoice id",
    )
    _run_check(
        report,
        "evidence_get_record_changes",
        "tool",
        lambda: server.evidence_get_record_changes(evidence="faktura-vydana", id=inv_id),
        skip_reason=None if inv_id else "no issued invoice id",
    )
    atts = _run_check(
        report,
        "evidence_list_attachments",
        "tool",
        lambda: server.evidence_list_attachments(evidence="faktura-vydana", id=inv_id),
        skip_reason=None if inv_id else "no issued invoice id",
    )
    attachment_id = None
    if atts is not None:
        parsed_atts = _parse_payload(atts)
        if isinstance(parsed_atts, list) and parsed_atts:
            first_att = parsed_atts[0]
            if isinstance(first_att, dict) and first_att.get("id") is not None:
                attachment_id = str(first_att["id"])
        elif isinstance(parsed_atts, dict):
            # some clients wrap attachments
            for key in ("priloha", "prilohy", "attachments", "records"):
                items = parsed_atts.get(key)
                if isinstance(items, list) and items and isinstance(items[0], dict):
                    if items[0].get("id") is not None:
                        attachment_id = str(items[0]["id"])
                        break
    _run_check(
        report,
        "contact_get_notification_email",
        "tool",
        lambda: server.contact_get_notification_email(id=contact_id),
        skip_reason=None if contact_id else "no contact id",
    )
    _run_check(
        report,
        "contact_get_cell_phone",
        "tool",
        lambda: server.contact_get_cell_phone(id=contact_id),
        skip_reason=None if contact_id else "no contact id",
    )
    _run_check(
        report,
        "contact_get_any_phone",
        "tool",
        lambda: server.contact_get_any_phone(id=contact_id),
        skip_reason=None if contact_id else "no contact id",
    )
    _run_check(
        report,
        "contact_get_bank_accounts",
        "tool",
        lambda: server.contact_get_bank_accounts(id=contact_id),
        skip_reason=None if contact_id else "no contact id",
    )
    _run_check(
        report,
        "call_user_query",
        "tool",
        lambda: server.call_user_query(query_id="nonexistent-query-for-capability-probe"),
        require_data=False,
        skip_reason="needs a real saved user query id/code on this company",
    )
    _run_check(
        report,
        "evidence_get_attachment",
        "tool",
        lambda: server.evidence_get_attachment(
            evidence="faktura-vydana", id=inv_id, attachment_id=attachment_id
        ),
        skip_reason=None
        if (inv_id and attachment_id)
        else "needs a real attachment id on an issued invoice",
    )

    # Track which RO tools we explicitly covered
    covered = {r.name.split(":")[0] for r in report.results if r.kind == "tool"}

    # Any remaining read-only tools not covered above
    for t in tools:
        if not _tool_is_readonly(t):
            continue
        if t.name in covered:
            continue
        fn = fn_by_name.get(t.name)
        if not fn:
            report.add(
                CheckResult(
                    name=t.name,
                    kind="tool",
                    ok=False,
                    detail="registered in MCP but missing Python callable",
                )
            )
            continue
        report.add(
            CheckResult(
                name=t.name,
                kind="tool",
                ok=True,
                detail="no default args probe defined",
                skipped=True,
            )
        )

    # ---- READ_ONLY guard on mutating tools ----
    if read_only:
        sample_writes = [
            ("invoice_issued_create", lambda: server.invoice_issued_create(kod="MCP-TEST", firma="code:X")),
            ("contact_create", lambda: server.contact_create(kod="MCP-TEST", nazev="MCP Test")),
            ("evidence_delete", lambda: server.evidence_delete(evidence="faktura-vydana", id="1")),
            ("changes_enable", lambda: server.changes_enable()),
            (
                "abraflexi_client_call:write",
                lambda: server.abraflexi_client_call(
                    client_class="ReadWrite",
                    method="delete",
                    evidence="faktura-vydana",
                    init="1",
                ),
            ),
        ]
        for name, fn in sample_writes:
            try:
                raw = fn()
                # Should have raised; if it returned, treat as failure unless explicit refusal
                payload = _parse_payload(raw)
                refused = False
                if isinstance(payload, dict) and (
                    "read-only" in str(payload).lower() or payload.get("success") is False
                ):
                    refused = True
                report.add(
                    CheckResult(
                        name=f"readonly_guard:{name}",
                        kind="guard",
                        ok=refused,
                        detail="write returned without raising" if not refused else "refused in payload",
                        sample=str(payload)[:300],
                    )
                )
            except ValueError as exc:
                ok = "read-only" in str(exc).lower()
                report.add(
                    CheckResult(
                        name=f"readonly_guard:{name}",
                        kind="guard",
                        ok=ok,
                        detail=str(exc),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                report.add(
                    CheckResult(
                        name=f"readonly_guard:{name}",
                        kind="guard",
                        ok=False,
                        detail=f"unexpected {type(exc).__name__}: {exc}",
                    )
                )

        # Read method via abraflexi_client_call should still work under READ_ONLY
        _run_check(
            report,
            "abraflexi_client_call:read",
            "tool",
            lambda: server.abraflexi_client_call(
                client_class="ReadOnly",
                method="get_properties",
                evidence="faktura-vydana",
            ),
        )

    # Ensure every RW tool at least has a catalog presence check
    for t in tools:
        if _tool_is_readonly(t):
            continue
        report.add(
            CheckResult(
                name=f"catalog:{t.name}",
                kind="meta",
                ok=True,
                detail="write tool registered (guard-sampled separately)",
            )
        )

    # Silence unused locals for linters
    _ = (rcv_id, product_id, bank_id, tool_by_name)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("ABRAFLEXI_URL"))
    parser.add_argument("--company", default=os.getenv("ABRAFLEXI_COMPANY"))
    parser.add_argument("--login", default=os.getenv("ABRAFLEXI_LOGIN"))
    parser.add_argument("--password", default=os.getenv("ABRAFLEXI_PASSWORD"))
    parser.add_argument("--json-out", help="Write full report JSON here")
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        help="Set READ_ONLY=false (not used for data checks; guards skipped)",
    )
    args = parser.parse_args()

    missing = [
        n
        for n, v in [
            ("--url/ABRAFLEXI_URL", args.url),
            ("--company/ABRAFLEXI_COMPANY", args.company),
            ("--login/ABRAFLEXI_LOGIN", args.login),
            ("--password/ABRAFLEXI_PASSWORD", args.password),
        ]
        if not v
    ]
    if missing:
        print(f"Missing required config: {', '.join(missing)}", file=sys.stderr)
        return 2

    report = run_scenario(
        args.url,
        args.company,
        args.login,
        args.password,
        read_only=not args.allow_writes,
    )

    print(f"AbraFlexi MCP live scenario: {report.url}/c/{report.company}/")
    print(f"passed={report.passed} failed={report.failed} skipped={report.skipped}")
    print()
    for r in report.results:
        if r.skipped:
            flag = "SKIP"
        elif r.ok:
            flag = "PASS"
        else:
            flag = "FAIL"
        print(f"  {flag:4} [{r.kind}] {r.name}: {r.detail}")

    if args.json_out:
        out = {
            "url": report.url,
            "company": report.company,
            "passed": report.passed,
            "failed": report.failed,
            "skipped": report.skipped,
            "results": [r.__dict__ for r in report.results],
        }
        Path(args.json_out).write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        print(f"\nWrote {args.json_out}")

    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
