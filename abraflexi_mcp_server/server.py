#!/usr/bin/env python3
"""
AbraFlexi MCP Server - Complete integration with AbraFlexi API using python-abraflexi

This server provides comprehensive access to AbraFlexi REST API functionality through
the Model Context Protocol (MCP), enabling AI assistants and other tools to
interact with AbraFlexi accounting systems.

Author: Vítězslav Dvořák
License: MIT
"""

import argparse
import os
import json
import logging
import base64
import inspect
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode
from fastmcp import FastMCP
from python_abraflexi import ReadOnly, ReadWrite, Changes, Adresar, FakturaVydana
from python_abraflexi.exceptions import AuthenticationException, PermissionException
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO if os.getenv("DEBUG") else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastMCP
mcp = FastMCP(
    "AbraFlexi MCP Server",
    instructions=(
        "This server is bound to exactly one AbraFlexi company for its entire "
        "process lifetime, set via the ABRAFLEXI_URL/ABRAFLEXI_COMPANY environment "
        "variables. Call the server_info tool to learn which company/URL this is. "
        "Every record returned by other tools (invoices, contacts, products, bank "
        "transactions, ...) already belongs to that one company by construction — "
        "it is never necessary or possible to ask this server for another company's "
        "data. Watch out for record fields that name a counterparty (e.g. an "
        "invoice's customer/supplier) — those describe the other party in the "
        "transaction, not the company this server is bound to."
    ),
)

# Global configuration
abraflexi_config: Optional[Dict[str, Any]] = None


def get_abraflexi_config() -> Dict[str, Any]:
    """Get AbraFlexi configuration from environment variables.
    
    Returns:
        Dict: Configuration dictionary
        
    Raises:
        ValueError: If required environment variables are missing
    """
    global abraflexi_config
    
    if abraflexi_config is None:
        url = os.getenv("ABRAFLEXI_URL")
        company = os.getenv("ABRAFLEXI_COMPANY")
        
        if not url:
            raise ValueError("ABRAFLEXI_URL environment variable is required")
        if not company:
            raise ValueError("ABRAFLEXI_COMPANY environment variable is required")
        
        logger.info(f"Initializing AbraFlexi configuration for {url}/{company}")
        
        abraflexi_config = {
            "url": url,
            "company": company,
            "user": os.getenv("ABRAFLEXI_LOGIN"),
            "password": os.getenv("ABRAFLEXI_PASSWORD"),
            "authSessionId": os.getenv("ABRAFLEXI_AUTHSESSID"),
            "timeout": int(os.getenv("ABRAFLEXI_TIMEOUT", "300")),
        }
        
        # Validate authentication
        if not abraflexi_config["authSessionId"] and not (
            abraflexi_config["user"] and abraflexi_config["password"]
        ):
            raise ValueError(
                "Either ABRAFLEXI_AUTHSESSID or ABRAFLEXI_LOGIN/ABRAFLEXI_PASSWORD must be set"
            )
        
        logger.info("Successfully configured AbraFlexi connection")
    
    return abraflexi_config


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def server_info() -> str:
    """Report which AbraFlexi company/instance this MCP server session is bound to.

    This server is bound to exactly one AbraFlexi company for its whole process
    lifetime (configured via ABRAFLEXI_URL/ABRAFLEXI_COMPANY). Every other tool's
    results already belong to this company by construction. Call this tool first
    whenever the identity of "the company" matters to the request (e.g. "how many
    invoices did company X issue"), instead of trying to infer it from record
    fields such as an invoice's customer/supplier name.

    Returns:
        str: JSON object with abraflexi_url, company, and read_only.
    """
    config = get_abraflexi_config()
    return format_response({
        "abraflexi_url": config["url"],
        "company": config["company"],
        "read_only": is_read_only(),
    })


def get_readonly_client(evidence: str, company: Optional[str] = None) -> ReadOnly:
    """Create a read-only AbraFlexi client for the specified evidence.

    Args:
        evidence: Evidence name (e.g., 'faktura-vydana', 'adresar')
        company: Company identifier (dbNazev) to query instead of the
            server's default ABRAFLEXI_COMPANY

    Returns:
        ReadOnly: Configured AbraFlexi client
    """
    config = get_abraflexi_config()
    options = {**config, "evidence": evidence}
    if company:
        options["company"] = company
    return ReadOnly(None, options)


def get_readwrite_client(evidence: str, company: Optional[str] = None) -> ReadWrite:
    """Create a read-write AbraFlexi client for the specified evidence.

    Args:
        evidence: Evidence name (e.g., 'faktura-vydana', 'adresar')
        company: Company identifier (dbNazev) to write to instead of the
            server's default ABRAFLEXI_COMPANY

    Returns:
        ReadWrite: Configured AbraFlexi client
    """
    config = get_abraflexi_config()
    options = {**config, "evidence": evidence}
    if company:
        options["company"] = company
    return ReadWrite(None, options)


def get_faktura_vydana_client(init: Optional[Union[int, str]] = None) -> FakturaVydana:
    """Create a FakturaVydana client, optionally loaded with a specific record.

    Args:
        init: Record ID, code, or None for an unloaded client

    Returns:
        FakturaVydana: Configured client
    """
    config = get_abraflexi_config()
    return FakturaVydana(init, config)


def get_adresar_client(init: Optional[Union[int, str]] = None) -> Adresar:
    """Create an Adresar client, optionally loaded with a specific record.

    Args:
        init: Record ID, code, or None for an unloaded client

    Returns:
        Adresar: Configured client
    """
    config = get_abraflexi_config()
    return Adresar(init, config)


def is_read_only() -> bool:
    """Check if server is in read-only mode.
    
    Returns:
        bool: True if read-only mode is enabled
    """
    return os.getenv("READ_ONLY", "true").lower() in ("true", "1", "yes")


def format_response(data: Any) -> str:
    """Format response data as JSON string.
    
    Args:
        data: Data to format
        
    Returns:
        str: JSON formatted string
    """
    if isinstance(data, bool):
        return json.dumps({"success": data})
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def format_records_response(
    data: Any,
    record_note: Optional[str] = None,
    company: Optional[str] = None,
) -> str:
    """Format a multi-record evidence response, wrapped with company context.

    Wraps the raw AbraFlexi records with a `_context` block naming which
    AbraFlexi company/URL the records were queried from, so the caller
    never has to infer whose data it is looking at from record fields.

    Args:
        data: Raw records (list or dict) from python-abraflexi
        record_note: Optional short note about field semantics for this
            evidence type (e.g. clarifying that a counterparty field is not
            the bound company)
        company: Company identifier the records were actually queried from,
            if it differs from the server's default ABRAFLEXI_COMPANY (e.g.
            evidence_get's optional company override)

    Returns:
        str: JSON formatted string with a _context envelope
    """
    config = get_abraflexi_config()
    return json.dumps(
        {
            "_context": {
                "abraflexi_company": company or config["company"],
                "abraflexi_url": config["url"],
                "note": record_note,
            },
            "records": data,
        },
        indent=2,
        default=str,
        ensure_ascii=False,
    )


def _serialize_result(data: Any) -> Any:
    """Serialize method-call results to JSON-safe values."""
    if isinstance(data, bytes):
        return {
            "type": "bytes_base64",
            "size_bytes": len(data),
            "data": base64.b64encode(data).decode("ascii"),
        }
    if isinstance(data, list):
        return [_serialize_result(item) for item in data]
    if isinstance(data, dict):
        return {str(key): _serialize_result(value) for key, value in data.items()}
    return data


def _build_client_options(
    evidence: Optional[str] = None,
    company: Optional[str] = None,
    extra_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build options for python-abraflexi client initialization."""
    options = dict(get_abraflexi_config())
    if company:
        options["company"] = company
    if evidence:
        options["evidence"] = evidence
    if extra_options:
        options.update(extra_options)
    return options


def _public_methods_for_class(cls: Any) -> List[str]:
    """Return sorted public callable method names for a class."""
    methods = []
    for name in dir(cls):
        if name.startswith("_"):
            continue
        attr = getattr(cls, name, None)
        if callable(attr):
            methods.append(name)
    return sorted(set(methods))


CLIENT_CLASS_MAP: Dict[str, Any] = {
    "ReadOnly": ReadOnly,
    "ReadWrite": ReadWrite,
    "Changes": Changes,
    "Adresar": Adresar,
    "FakturaVydana": FakturaVydana,
}


WRITE_METHOD_NAMES = {
    "insert_to_abraflexi",
    "update",
    "delete",
    "save",
    "perform_action",
    "copy",
    "lock",
    "unlock",
    "lock_for_ucetni",
    "storno",
    "mass_update",
    "set_atomic",
    "set_dry_run",
    "batch_insert",
    "batch_update",
    "add_attachment",
    "add_attachment_from_file",
    "delete_attachment",
    "set_label",
    "unset_label",
    "unset_labels",
    "set_sub_items",
    "add_array_to_branch",
    "match_payment",
    "cash_payment",
    "deduct_advance",
    "deduct_zdd",
    "link_zdd",
    "unlink_zdd",
    "enable",
    "disable",
}


def _instantiate_client(
    client_class: str,
    init: Optional[Union[int, str, Dict[str, Any]]] = None,
    evidence: Optional[str] = None,
    company: Optional[str] = None,
    extra_options: Optional[Dict[str, Any]] = None,
) -> Any:
    """Instantiate one of the supported python-abraflexi clients."""
    if client_class not in CLIENT_CLASS_MAP:
        raise ValueError(
            f"Unsupported client_class '{client_class}'. Supported: {', '.join(CLIENT_CLASS_MAP.keys())}"
        )

    cls = CLIENT_CLASS_MAP[client_class]
    options = _build_client_options(evidence=evidence, company=company, extra_options=extra_options)
    return cls(init, options)


def validate_read_only() -> None:
    """Validate that write operations are allowed.
    
    Raises:
        ValueError: If server is in read-only mode
    """
    if is_read_only():
        raise ValueError("Server is in read-only mode - write operations are not allowed")


def _require_record_identifier(
    id: Optional[str] = None,
    kod: Optional[str] = None,
) -> Union[int, str]:
    """Resolve a record id or code into an AbraFlexi identifier."""
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")
    return int(id) if id else f"code:{kod}"


# Annotations for tools that only read AbraFlexi state (may still write a
# local file as an output side-effect).
_RO_ANN = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}


# ISSUED INVOICES (Faktura Vydaná)
@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def invoice_issued_get(
    ids: Optional[List[str]] = None,
    kod: Optional[str] = None,
    datum_vystaveni_od: Optional[str] = None,
    datum_vystaveni_do: Optional[str] = None,
    filter_expr: Optional[str] = None,
    limit: Optional[int] = None,
    detail: str = "summary",
    add_row_count: bool = False
) -> str:
    """Get issued invoices (faktura-vydana) from AbraFlexi.

    Every invoice returned was issued BY the AbraFlexi company this server is
    bound to (see server_info) - there is no way to query another company's
    invoices from this server. The 'nazFirmy'/'firma' fields on each record
    identify the CUSTOMER/counterparty being invoiced, not the issuer.

    Args:
        ids: List of invoice IDs to retrieve
        kod: Invoice code to search for
        datum_vystaveni_od: Lower bound for issue date (YYYY-MM-DD, inclusive)
        datum_vystaveni_do: Upper bound for issue date (YYYY-MM-DD, inclusive)
        filter_expr: Additional AbraFlexi filter expression to combine with built-in filters
        limit: Maximum number of results
        detail: Detail level (summary, id, full, custom:field1,field2)
        add_row_count: Include the total number of matching records in the response

    Returns:
        str: JSON object with a _context block (bound company/URL) and a
            records list of invoices
    """
    client = get_readonly_client("faktura-vydana")
    
    # Build filter
    filters = []
    if ids:
        filters.append(f"id in ({','.join(ids)})")
    if kod:
        filters.append(f"kod='{kod}'")
    if datum_vystaveni_od:
        filters.append(f"datVyst >= '{datum_vystaveni_od}'")
    if datum_vystaveni_do:
        filters.append(f"datVyst <= '{datum_vystaveni_do}'")
    if filter_expr:
        filters.append(f"({filter_expr})")
    
    if filters:
        client.filter = " AND ".join(filters)
    
    client.default_url_params["detail"] = detail
    if limit:
        client.default_url_params["limit"] = limit
    if add_row_count:
        client.set_add_row_count(True)
    
    result = client.get_all_from_abraflexi()
    return format_records_response(
        result,
        record_note=(
            "All invoices below were issued by the AbraFlexi company this "
            "server is bound to (see abraflexi_company above / server_info "
            "tool). 'nazFirmy'/'firma' identify the customer/counterparty "
            "being invoiced, not the issuer."
        ),
    )


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def invoice_issued_create(
    kod: str,
    firma: str,
    datum_vystaveni: Optional[str] = None,
    polozky: Optional[List[Dict[str, Any]]] = None,
    extra_fields: Optional[Dict[str, Any]] = None
) -> str:
    """Create a new issued invoice in AbraFlexi.
    
    Args:
        kod: Invoice code (unique identifier)
        firma: Customer reference (e.g., 'code:CUSTOMER01')
        datum_vystaveni: Issue date (YYYY-MM-DD format)
        polozky: Invoice items/lines
        extra_fields: Additional invoice fields
        
    Returns:
        str: JSON formatted creation result
    """
    validate_read_only()
    
    client = get_readwrite_client("faktura-vydana")
    
    # Set required fields
    client.set_data_value("kod", kod)
    client.set_data_value("firma", firma)
    
    if datum_vystaveni:
        client.set_data_value("datVyst", datum_vystaveni)
    
    if polozky:
        client.set_data_value("polozkyFaktury", polozky)
    
    # Set additional fields
    if extra_fields:
        for key, value in extra_fields.items():
            client.set_data_value(key, value)
    
    result = client.insert_to_abraflexi()
    
    return format_response({
        "success": result,
        "id": client.last_inserted_id,
        "kod": kod
    })


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def invoice_issued_update(
    id: Optional[str] = None,
    kod: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None
) -> str:
    """Update an existing issued invoice in AbraFlexi.
    
    Args:
        id: Invoice ID to update
        kod: Invoice code to update (alternative to id)
        data: Fields to update
        
    Returns:
        str: JSON formatted update result
    """
    validate_read_only()
    
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")
    
    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client("faktura-vydana")
    
    # Load existing invoice
    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Invoice not found: {identifier}")
    
    # Update fields
    if data:
        for key, value in data.items():
            client.set_data_value(key, value)
    
    result = client.update()
    
    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True})
def invoice_issued_delete(id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Delete an issued invoice from AbraFlexi.
    
    Args:
        id: Invoice ID to delete
        kod: Invoice code to delete (alternative to id)
        
    Returns:
        str: JSON formatted deletion result
    """
    validate_read_only()
    
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")
    
    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client("faktura-vydana")
    
    # Load and delete
    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Invoice not found: {identifier}")
    
    result = client.delete()
    
    return format_response({"success": result})


# RECEIVED INVOICES (Faktura Přijatá)
@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def invoice_received_get(
    ids: Optional[List[str]] = None,
    kod: Optional[str] = None,
    limit: Optional[int] = None,
    detail: str = "summary"
) -> str:
    """Get received invoices (faktura-prijata) from AbraFlexi.

    Every invoice returned was received BY the AbraFlexi company this server
    is bound to (see server_info) - there is no way to query another
    company's received invoices from this server. The 'nazFirmy'/'firma'
    fields on each record identify the SUPPLIER/counterparty who issued the
    invoice, not the receiving company.

    Args:
        ids: List of invoice IDs to retrieve
        kod: Invoice code to search for
        limit: Maximum number of results
        detail: Detail level (summary, id, full, custom:field1,field2)

    Returns:
        str: JSON object with a _context block (bound company/URL) and a
            records list of invoices
    """
    client = get_readonly_client("faktura-prijata")
    
    # Build filter
    filters = []
    if ids:
        filters.append(f"id in ({','.join(ids)})")
    if kod:
        filters.append(f"kod='{kod}'")
    
    if filters:
        client.filter = " AND ".join(filters)
    
    client.default_url_params["detail"] = detail
    if limit:
        client.default_url_params["limit"] = limit
    
    result = client.get_all_from_abraflexi()
    return format_records_response(
        result,
        record_note=(
            "All invoices below were received by the AbraFlexi company this "
            "server is bound to (see abraflexi_company above / server_info "
            "tool). 'nazFirmy'/'firma' identify the supplier/counterparty "
            "who issued the invoice, not the receiving company."
        ),
    )


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def invoice_received_create(
    kod: str,
    firma: str,
    datum_vystaveni: Optional[str] = None,
    polozky: Optional[List[Dict[str, Any]]] = None,
    extra_fields: Optional[Dict[str, Any]] = None
) -> str:
    """Create a new received invoice in AbraFlexi.
    
    Args:
        kod: Invoice code (unique identifier)
        firma: Supplier reference (e.g., 'code:SUPPLIER01')
        datum_vystaveni: Issue date (YYYY-MM-DD format)
        polozky: Invoice items/lines
        extra_fields: Additional invoice fields
        
    Returns:
        str: JSON formatted creation result
    """
    validate_read_only()
    
    client = get_readwrite_client("faktura-prijata")
    
    # Set required fields
    client.set_data_value("kod", kod)
    client.set_data_value("firma", firma)
    
    if datum_vystaveni:
        client.set_data_value("datVyst", datum_vystaveni)
    
    if polozky:
        client.set_data_value("polozkyFaktury", polozky)
    
    # Set additional fields
    if extra_fields:
        for key, value in extra_fields.items():
            client.set_data_value(key, value)
    
    result = client.insert_to_abraflexi()
    
    return format_response({
        "success": result,
        "id": client.last_inserted_id,
        "kod": kod
    })


# COMPANY MANAGEMENT (founding new accounting units)
@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def company_create(
    name: str,
    country: str = "CZ",
    org_type: Optional[str] = None,
    ic: Optional[str] = None,
    vatid: Optional[str] = None,
    use_demo: bool = False,
    extra_fields: Optional[Dict[str, Any]] = None
) -> str:
    """Create a brand-new AbraFlexi company (accounting unit) at the server root.

    Unlike every other *_create tool, this does NOT operate on the company
    configured via ABRAFLEXI_COMPANY - it calls the server-level
    "/admin/zalozeni-firmy" endpoint, which requires a REST user with
    server-admin/license-level rights (not just rights on one company).

    Args:
        name: Display name of the new company. The company identifier
            (dbNazev, used as {company} in later /c/{company}/... calls) is
            derived from this automatically.
        country: Legislation - "CZ" or "SK".
        org_type: Organization type, e.g. "PODNIKATELE+PU" (double-entry
            bookkeeping), "PODNIKATELE+DE" (tax records), "NEZISKOVE",
            "ROZPOCTOVE" for CZ; "PODNIKATELIA+PU" for SK.
        ic: Company registration number (ICO) - auto-fills VAT payer
            status, registered seat and other fields from the ARES registry.
        vatid: VAT ID (DIC), if not auto-filled via ic.
        use_demo: Seed the new company with demo data (CZ + PODNIKATELE+PU only).
        extra_fields: Any additional query parameters to pass through.

    Returns:
        str: JSON with success, the new company's dbNazev (identifier) and
            full URL, parsed from the response's Location header.

    Raises:
        ValueError: If the configured REST user lacks server-admin/license
            rights to create companies (AbraFlexi returns 401/402/403).
    """
    validate_read_only()

    config = get_abraflexi_config()
    client = ReadOnly(None, {**config, "evidence": None})

    params: Dict[str, str] = {"name": name, "country": country}
    if org_type:
        params["org-type"] = org_type
    if ic:
        params["ic"] = ic
    if vatid:
        params["vatid"] = vatid
    if use_demo:
        params["use-demo"] = "true"
    if extra_fields:
        params.update({key: str(value) for key, value in extra_fields.items()})

    path = "admin/zalozeni-firmy?" + urlencode(params)

    try:
        client._perform_root_request(path, "PUT")
    except (AuthenticationException, PermissionException) as exc:
        raise ValueError(
            "Cannot create a new AbraFlexi company: the configured REST "
            "user lacks server-admin/license rights required for company "
            f"creation ({exc})"
        ) from exc

    location = ""
    if client.last_response is not None:
        location = client.last_response.headers.get("Location", "")

    db_nazev = location.rstrip("/").split("/")[-1] if location else None
    if db_nazev and db_nazev.endswith(".json"):
        db_nazev = db_nazev[: -len(".json")]

    return format_response({
        "success": True,
        "dbNazev": db_nazev,
        "url": location,
    })


# CONTACTS/COMPANIES (Adresář)
@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def contact_get(
    ids: Optional[List[str]] = None,
    kod: Optional[str] = None,
    nazev: Optional[str] = None,
    limit: Optional[int] = None,
    detail: str = "summary"
) -> str:
    """Get contacts/companies (adresar) from AbraFlexi.

    These are address-book entries (customers, suppliers, other contacts)
    belonging to the AbraFlexi company this server is bound to (see
    server_info) - they are business partners of that company, not the
    company itself.

    Args:
        ids: List of contact IDs to retrieve
        kod: Contact code to search for
        nazev: Contact name to search for (partial match)
        limit: Maximum number of results
        detail: Detail level (summary, id, full, custom:field1,field2)

    Returns:
        str: JSON object with a _context block (bound company/URL) and a
            records list of contacts
    """
    client = get_readonly_client("adresar")
    
    # Build filter
    filters = []
    if ids:
        filters.append(f"id in ({','.join(ids)})")
    if kod:
        filters.append(f"kod='{kod}'")
    if nazev:
        # AbraFlexi's `like` is a plain case-insensitive substring match and
        # takes no wildcards; wrapping the term in '*...*' makes it search for
        # a literal '*' and never matches.
        filters.append(f"nazev like '{nazev}'")
    
    if filters:
        client.filter = " AND ".join(filters)
    
    client.default_url_params["detail"] = detail
    if limit:
        client.default_url_params["limit"] = limit
    
    result = client.get_all_from_abraflexi()
    return format_records_response(
        result,
        record_note=(
            "All contacts below are address-book entries (business "
            "partners) of the AbraFlexi company this server is bound to "
            "(see abraflexi_company above / server_info tool), not the "
            "company itself."
        ),
    )


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def contact_create(
    kod: str,
    nazev: str,
    email: Optional[str] = None,
    tel: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None
) -> str:
    """Create a new contact/company in AbraFlexi.
    
    Args:
        kod: Contact code (unique identifier)
        nazev: Contact name
        email: Email address
        tel: Phone number
        extra_fields: Additional contact fields
        
    Returns:
        str: JSON formatted creation result
    """
    validate_read_only()
    
    client = get_readwrite_client("adresar")
    
    # Set required fields
    client.set_data_value("kod", kod)
    client.set_data_value("nazev", nazev)
    
    if email:
        client.set_data_value("email", email)
    if tel:
        client.set_data_value("tel", tel)
    
    # Set additional fields
    if extra_fields:
        for key, value in extra_fields.items():
            client.set_data_value(key, value)
    
    result = client.insert_to_abraflexi()
    
    return format_response({
        "success": result,
        "id": client.last_inserted_id,
        "kod": kod
    })


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def contact_update(
    id: Optional[str] = None,
    kod: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None
) -> str:
    """Update an existing contact/company in AbraFlexi.
    
    Args:
        id: Contact ID to update
        kod: Contact code to update (alternative to id)
        data: Fields to update
        
    Returns:
        str: JSON formatted update result
    """
    validate_read_only()
    
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")
    
    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client("adresar")
    
    # Load existing contact
    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Contact not found: {identifier}")
    
    # Update fields
    if data:
        for key, value in data.items():
            client.set_data_value(key, value)
    
    result = client.update()
    
    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True})
def contact_delete(id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Delete a contact/company from AbraFlexi.
    
    Args:
        id: Contact ID to delete
        kod: Contact code to delete (alternative to id)
        
    Returns:
        str: JSON formatted deletion result
    """
    validate_read_only()
    
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")
    
    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client("adresar")
    
    # Load and delete
    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Contact not found: {identifier}")
    
    result = client.delete()
    
    return format_response({"success": result})


# PRODUCTS (Ceník)
@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def product_get(
    ids: Optional[List[str]] = None,
    kod: Optional[str] = None,
    nazev: Optional[str] = None,
    limit: Optional[int] = None,
    detail: str = "summary"
) -> str:
    """Get products (cenik) from AbraFlexi.

    These are price-list entries belonging to the AbraFlexi company this
    server is bound to (see server_info).

    Args:
        ids: List of product IDs to retrieve
        kod: Product code to search for
        nazev: Product name to search for (partial match)
        limit: Maximum number of results
        detail: Detail level (summary, id, full, custom:field1,field2)

    Returns:
        str: JSON object with a _context block (bound company/URL) and a
            records list of products
    """
    client = get_readonly_client("cenik")
    
    # Build filter
    filters = []
    if ids:
        filters.append(f"id in ({','.join(ids)})")
    if kod:
        filters.append(f"kod='{kod}'")
    if nazev:
        # AbraFlexi's `like` is a plain case-insensitive substring match and
        # takes no wildcards; wrapping the term in '*...*' makes it search for
        # a literal '*' and never matches.
        filters.append(f"nazev like '{nazev}'")
    
    if filters:
        client.filter = " AND ".join(filters)
    
    client.default_url_params["detail"] = detail
    if limit:
        client.default_url_params["limit"] = limit
    
    result = client.get_all_from_abraflexi()
    return format_records_response(
        result,
        record_note=(
            "All products below belong to the price list of the AbraFlexi "
            "company this server is bound to (see abraflexi_company above / "
            "server_info tool)."
        ),
    )


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def product_create(
    kod: str,
    nazev: str,
    cena: Optional[float] = None,
    extra_fields: Optional[Dict[str, Any]] = None
) -> str:
    """Create a new product in AbraFlexi.
    
    Args:
        kod: Product code (unique identifier)
        nazev: Product name
        cena: Product price
        extra_fields: Additional product fields
        
    Returns:
        str: JSON formatted creation result
    """
    validate_read_only()
    
    client = get_readwrite_client("cenik")
    
    # Set required fields
    client.set_data_value("kod", kod)
    client.set_data_value("nazev", nazev)
    
    if cena is not None:
        client.set_data_value("cenaZakl", cena)
    
    # Set additional fields
    if extra_fields:
        for key, value in extra_fields.items():
            client.set_data_value(key, value)
    
    result = client.insert_to_abraflexi()
    
    return format_response({
        "success": result,
        "id": client.last_inserted_id,
        "kod": kod
    })


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def product_update(
    id: Optional[str] = None,
    kod: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None
) -> str:
    """Update an existing product in AbraFlexi.
    
    Args:
        id: Product ID to update
        kod: Product code to update (alternative to id)
        data: Fields to update
        
    Returns:
        str: JSON formatted update result
    """
    validate_read_only()
    
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")
    
    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client("cenik")
    
    # Load existing product
    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Product not found: {identifier}")
    
    # Update fields
    if data:
        for key, value in data.items():
            client.set_data_value(key, value)
    
    result = client.update()
    
    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True})
def product_delete(id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Delete a product from AbraFlexi.
    
    Args:
        id: Product ID to delete
        kod: Product code to delete (alternative to id)
        
    Returns:
        str: JSON formatted deletion result
    """
    validate_read_only()
    
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")
    
    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client("cenik")
    
    # Load and delete
    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Product not found: {identifier}")
    
    result = client.delete()
    
    return format_response({"success": result})


# BANK TRANSACTIONS (Banka)
@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def bank_transaction_get(
    ids: Optional[List[str]] = None,
    limit: Optional[int] = None,
    detail: str = "summary"
) -> str:
    """Get bank transactions (banka) from AbraFlexi.

    These are bank transactions belonging to the AbraFlexi company this
    server is bound to (see server_info).

    Args:
        ids: List of transaction IDs to retrieve
        limit: Maximum number of results
        detail: Detail level (summary, id, full, custom:field1,field2)

    Returns:
        str: JSON object with a _context block (bound company/URL) and a
            records list of bank transactions
    """
    client = get_readonly_client("banka")

    # Build filter
    if ids:
        client.filter = f"id in ({','.join(ids)})"

    client.default_url_params["detail"] = detail
    if limit:
        client.default_url_params["limit"] = limit

    result = client.get_all_from_abraflexi()
    return format_records_response(
        result,
        record_note=(
            "All transactions below belong to the AbraFlexi company this "
            "server is bound to (see abraflexi_company above / server_info "
            "tool)."
        ),
    )


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def bank_transaction_create(
    kod: str,
    banka: str,
    datum_vystaveni: str,
    castka: float,
    typ_pohybu: str = "prijem",
    typ_dokladu: str = "STANDARD",
    popis: Optional[str] = None,
    firma: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None
) -> str:
    """Create a new bank transaction in AbraFlexi.

    Args:
        kod: Transaction code (unique identifier)
        banka: Bank account reference (e.g., 'code:BANKA-CZK')
        datum_vystaveni: Transaction date (YYYY-MM-DD format)
        castka: Transaction amount, VAT-exempt (sets sumOsv on an
            itemless document; use extra_fields for a VAT-split amount
            or actual polozkyDokladu line items instead)
        typ_pohybu: Movement direction - 'prijem' (income, default) or
            'vydej' (expense)
        typ_dokladu: Document type code (see the typ-banka evidence);
            defaults to 'STANDARD'
        popis: Transaction description
        firma: Related contact reference (e.g., 'code:CUSTOMER01')
        extra_fields: Additional transaction fields

    Returns:
        str: JSON formatted creation result
    """
    validate_read_only()

    client = get_readwrite_client("banka")

    # Set required fields
    client.set_data_value("kod", kod)
    client.set_data_value("banka", banka)
    client.set_data_value("datVyst", datum_vystaveni)
    client.set_data_value("typDokl", f"code:{typ_dokladu}")
    client.set_data_value("typPohybuK", f"typPohybu.{typ_pohybu}")
    # Without line items, the amount can only be set via sumOsv/sumZkl*
    # on an explicitly itemless ("bezPolozek") document - AbraFlexi
    # rejects a directly-set sumCelkem/sumOsv otherwise, since it's
    # normally computed from polozkyDokladu.
    client.set_data_value("bezPolozek", True)
    client.set_data_value("sumOsv", castka)

    if popis:
        client.set_data_value("popis", popis)
    if firma:
        client.set_data_value("firma", firma)

    # Set additional fields
    if extra_fields:
        for key, value in extra_fields.items():
            client.set_data_value(key, value)

    result = client.insert_to_abraflexi()

    return format_response({
        "success": result,
        "id": client.last_inserted_id,
        "kod": kod
    })


# GENERIC EVIDENCE OPERATIONS
@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_get(
    evidence: str,
    ids: Optional[List[str]] = None,
    filter_expr: Optional[str] = None,
    limit: Optional[int] = None,
    detail: str = "summary",
    start: Optional[int] = None,
    order: Optional[str] = None,
    order_direction: str = "A",
    add_row_count: bool = False,
    relations: Optional[List[str]] = None,
    company: Optional[str] = None
) -> str:
    """Get records from any AbraFlexi evidence.

    Args:
        evidence: Evidence name (e.g., 'faktura-vydana', 'adresar', 'cenik')
        ids: List of record IDs to retrieve
        filter_expr: AbraFlexi filter expression
        limit: Maximum number of results
        detail: Detail level (summary, id, full, custom:field1,field2)
        start: Zero-based offset of the first record to return (pagination)
        order: Column name to sort by
        order_direction: "A" for ascending (default) or "D" for descending
        add_row_count: Include the total number of matching records in the response
        relations: Sub-evidences to include in the response (e.g. ['polozkyFaktury'])
        company: Company identifier (dbNazev) to query instead of the
            server's default ABRAFLEXI_COMPANY - e.g. to read another
            company's 'uzivatele' (user access) evidence

    Returns:
        str: JSON object with a _context block (the company actually
            queried - the override above, or the server's bound default -
            plus its URL) and a records list
    """
    client = get_readonly_client(evidence, company=company)

    # Build filter
    if ids:
        client.filter = f"id in ({','.join(ids)})"
    elif filter_expr:
        client.filter = filter_expr

    client.default_url_params["detail"] = detail
    if limit:
        client.default_url_params["limit"] = limit
    if start is not None:
        client.set_start(start)
    if order:
        client.set_order(order, order_direction)
    if add_row_count:
        client.set_add_row_count(True)
    if relations:
        client.set_relations(*relations)

    result = client.get_all_from_abraflexi()
    return format_records_response(
        result,
        record_note=(
            "Records below belong to the AbraFlexi company named in "
            "abraflexi_company above (the 'company' override if given, "
            "otherwise the server's bound default - see server_info)."
        ),
        company=company,
    )


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def evidence_create(evidence: str, data: Dict[str, Any], company: Optional[str] = None) -> str:
    """Create a new record in any AbraFlexi evidence.

    Args:
        evidence: Evidence name (e.g., 'faktura-vydana', 'adresar', 'cenik')
        data: Record data as dictionary
        company: Company identifier (dbNazev) to write to instead of the
            server's default ABRAFLEXI_COMPANY - e.g. to grant a user
            access by inserting into another company's 'uzivatele' evidence

    Returns:
        str: JSON formatted creation result
    """
    validate_read_only()

    client = get_readwrite_client(evidence, company=company)
    
    # Set all data fields
    for key, value in data.items():
        client.set_data_value(key, value)
    
    result = client.insert_to_abraflexi()
    
    return format_response({
        "success": result,
        "id": client.last_inserted_id
    })


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_update(
    evidence: str,
    id: Optional[str] = None,
    kod: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    remove_external_ids: Optional[str] = None,
    company: Optional[str] = None
) -> str:
    """Update a record in any AbraFlexi evidence.

    Args:
        evidence: Evidence name (e.g., 'faktura-vydana', 'adresar', 'cenik')
        id: Record ID to update
        kod: Record code to update (alternative to id)
        data: Fields to update as dictionary
        remove_external_ids: If given, remove external identifiers starting
            with this prefix (empty string removes all of them) as part of
            the update
        company: Company identifier (dbNazev) to write to instead of the
            server's default ABRAFLEXI_COMPANY

    Returns:
        str: JSON formatted update result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client(evidence, company=company)

    # Load existing record
    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    # Update fields
    if data:
        for key, value in data.items():
            client.set_data_value(key, value)

    result = client.update(remove_external_ids=remove_external_ids)

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True})
def evidence_delete(
    evidence: str,
    id: Optional[str] = None,
    kod: Optional[str] = None,
    company: Optional[str] = None
) -> str:
    """Delete a record from any AbraFlexi evidence.

    Args:
        evidence: Evidence name (e.g., 'faktura-vydana', 'adresar', 'cenik')
        id: Record ID to delete
        kod: Record code to delete (alternative to id)
        company: Company identifier (dbNazev) to delete from instead of the
            server's default ABRAFLEXI_COMPANY

    Returns:
        str: JSON formatted deletion result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client(evidence, company=company)

    # Load and delete
    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    result = client.delete()

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def evidence_attach_file(
    evidence: str,
    filepath: str,
    id: Optional[str] = None,
    kod: Optional[str] = None
) -> str:
    """Attach a local file to a record in any AbraFlexi evidence.

    Args:
        evidence: Evidence name (e.g., 'cenik', 'adresar')
        filepath: Path to the local file to attach (read from this server's filesystem)
        id: Record ID to attach the file to
        kod: Record code to attach the file to (alternative to id)

    Returns:
        str: JSON formatted result with the created attachment's ID
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client(evidence)

    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    attachment_id = client.add_attachment_from_file(filepath)

    return format_response({
        "success": attachment_id is not None,
        "attachment_id": attachment_id
    })


# ACTIONS, LOCKING & BATCH OPERATIONS
@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_lock(evidence: str, id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Lock a record in any AbraFlexi evidence, preventing further changes until unlocked.

    Args:
        evidence: Evidence name (e.g., 'faktura-vydana', 'adresar', 'cenik')
        id: Record ID to lock
        kod: Record code to lock (alternative to id)

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client(evidence)

    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    result = client.lock()

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_unlock(evidence: str, id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Unlock a record in any AbraFlexi evidence.

    Args:
        evidence: Evidence name (e.g., 'faktura-vydana', 'adresar', 'cenik')
        id: Record ID to unlock
        kod: Record code to unlock (alternative to id)

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client(evidence)

    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    result = client.unlock()

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_lock_for_ucetni(evidence: str, id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Lock a record in any AbraFlexi evidence for the accountant (lock-for-ucetni).

    Args:
        evidence: Evidence name (e.g., 'faktura-vydana', 'adresar', 'cenik')
        id: Record ID to lock
        kod: Record code to lock (alternative to id)

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client(evidence)

    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    result = client.lock_for_ucetni()

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True})
def evidence_storno(evidence: str, id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Cancel (storno) a document record in any AbraFlexi evidence.

    Args:
        evidence: Evidence name (e.g., 'faktura-vydana', 'faktura-prijata')
        id: Record ID to cancel
        kod: Record code to cancel (alternative to id)

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client(evidence)

    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    result = client.storno()

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
def evidence_perform_action(
    evidence: str,
    action: str,
    id: Optional[str] = None,
    kod: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None
) -> str:
    """Perform a custom business action on a record via its dedicated
    {id}/{action}.json URL (e.g. paying an invoice), as opposed to the
    body-level @action attribute used by evidence_lock/evidence_storno/etc.

    Args:
        evidence: Evidence name (e.g., 'faktura-vydana')
        action: Action name (e.g., 'pay')
        id: Record ID to act on
        kod: Record code to act on (alternative to id)
        params: Action parameters

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client(evidence)

    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    result = client.perform_action(action, params)

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_mass_update(
    evidence: str,
    filter_expr: str,
    data: Optional[Dict[str, Any]] = None,
    action: Optional[str] = None
) -> str:
    """Update, or perform an action on, every record of an evidence matching
    a filter in a single request (Davkove operace).

    Args:
        evidence: Evidence name (e.g., 'cenik')
        filter_expr: AbraFlexi filter expression selecting the records to affect
        data: Fields to set on every matching record
        action: If given, perform this action (e.g. 'lock') on every matching
            record instead of (or in addition to) updating fields

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    client = get_readwrite_client(evidence)
    result = client.mass_update(filter_expr, data, action=action)

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def evidence_batch_insert(
    evidence: str,
    records: List[Dict[str, Any]],
    atomic: bool = False,
    dry_run: bool = False
) -> str:
    """Insert multiple records into an evidence in a single request.

    Args:
        evidence: Evidence name
        records: List of records to insert
        atomic: Commit each record independently instead of the whole batch
            as one all-or-nothing transaction
        dry_run: Validate the batch without persisting anything

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    client = get_readwrite_client(evidence)
    if atomic:
        client.set_atomic(True)
    if dry_run:
        client.set_dry_run(True)

    result = client.batch_insert(records)

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_batch_update(
    evidence: str,
    records: List[Dict[str, Any]],
    atomic: bool = False,
    dry_run: bool = False
) -> str:
    """Update multiple records in an evidence in a single request.

    Args:
        evidence: Evidence name
        records: List of records to update (each must include 'id' or 'kod')
        atomic: Commit each record independently instead of the whole batch
            as one all-or-nothing transaction
        dry_run: Validate the batch without persisting anything

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    client = get_readwrite_client(evidence)
    if atomic:
        client.set_atomic(True)
    if dry_run:
        client.set_dry_run(True)

    result = client.batch_update(records)

    return format_response({"success": result})


# ATTACHMENTS (listing, metadata, download, thumbnail, delete)
# Attachment GETs use ReadOnly.perform_request — python-abraflexi only exposes
# convenience wrappers on ReadWrite, but the HTTP paths are read-only.
@mcp.tool(annotations=_RO_ANN)
def evidence_list_attachments(evidence: str, id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """List attachments (prilohy) of a record in any AbraFlexi evidence.

    Args:
        evidence: Evidence name
        id: Record ID
        kod: Record code (alternative to id)

    Returns:
        str: JSON formatted list of attachments
    """
    identifier = _require_record_identifier(id, kod)
    client = get_readonly_client(evidence)
    result = client.perform_request(url_suffix=f"{identifier}/prilohy.json")
    return format_response(result)


@mcp.tool(annotations=_RO_ANN)
def evidence_get_attachment(
    evidence: str,
    attachment_id: str,
    id: Optional[str] = None,
    kod: Optional[str] = None
) -> str:
    """Get metadata for a single attachment of a record.

    Args:
        evidence: Evidence name
        attachment_id: Attachment record identifier
        id: Record ID
        kod: Record code (alternative to id)

    Returns:
        str: JSON formatted attachment metadata
    """
    identifier = _require_record_identifier(id, kod)
    client = get_readonly_client(evidence)
    result = client.perform_request(
        url_suffix=f"{identifier}/prilohy/{attachment_id}.json"
    )
    return format_response(result)


@mcp.tool(annotations=_RO_ANN)
def evidence_download_attachment(
    evidence: str,
    attachment_id: str,
    output_path: str,
    id: Optional[str] = None,
    kod: Optional[str] = None
) -> str:
    """Download an attachment's raw content to a local file.

    Does not modify AbraFlexi data; only writes ``output_path`` on the MCP host.

    Args:
        evidence: Evidence name
        attachment_id: Attachment record identifier
        output_path: Local filesystem path to write the downloaded content to
        id: Record ID
        kod: Record code (alternative to id)

    Returns:
        str: JSON formatted result with the written file path and size
    """
    identifier = _require_record_identifier(id, kod)
    client = get_readonly_client(evidence)
    content = client.perform_request(
        url_suffix=f"{identifier}/prilohy/{attachment_id}/content",
        binary=True,
    )
    if not content:
        raise ValueError(f"Attachment not found: {attachment_id}")

    with open(output_path, "wb") as fh:
        fh.write(content)

    return format_response({"success": True, "path": output_path, "size_bytes": len(content)})


@mcp.tool(annotations=_RO_ANN)
def evidence_get_attachment_thumbnail(
    evidence: str,
    attachment_id: str,
    output_path: str,
    id: Optional[str] = None,
    kod: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None
) -> str:
    """Download the thumbnail of an image attachment to a local file.

    Does not modify AbraFlexi data; only writes ``output_path`` on the MCP host.

    Args:
        evidence: Evidence name
        attachment_id: Attachment record identifier
        output_path: Local filesystem path to write the thumbnail to
        id: Record ID
        kod: Record code (alternative to id)
        width: Requested thumbnail width in pixels
        height: Requested thumbnail height in pixels

    Returns:
        str: JSON formatted result with the written file path and size
    """
    identifier = _require_record_identifier(id, kod)
    suffix = f"{identifier}/prilohy/{attachment_id}/thumbnail"
    params = []
    if width:
        params.append(f"w={width}")
    if height:
        params.append(f"h={height}")
    if params:
        suffix += "?" + "&".join(params)

    client = get_readonly_client(evidence)
    content = client.perform_request(url_suffix=suffix, binary=True)
    if not content:
        raise ValueError(f"Thumbnail not found for attachment: {attachment_id}")

    with open(output_path, "wb") as fh:
        fh.write(content)

    return format_response({"success": True, "path": output_path, "size_bytes": len(content)})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True})
def evidence_delete_attachment(
    evidence: str,
    attachment_id: str,
    id: Optional[str] = None,
    kod: Optional[str] = None
) -> str:
    """Delete an attachment from a record.

    Args:
        evidence: Evidence name
        attachment_id: Attachment record identifier to delete
        id: Record ID
        kod: Record code (alternative to id)

    Returns:
        str: JSON formatted deletion result
    """
    validate_read_only()

    identifier = _require_record_identifier(id, kod)
    client = get_readwrite_client(evidence)

    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    result = client.delete_attachment(attachment_id)

    return format_response({"success": result})


# REPORTS, QR CODES & USER QUERIES
@mcp.tool(annotations=_RO_ANN)
def evidence_export_report(
    evidence: str,
    output_path: str,
    id: Optional[str] = None,
    kod: Optional[str] = None,
    report_format: str = "pdf",
    report_name: Optional[str] = None,
    report_lang: Optional[str] = None,
    report_sign: bool = False
) -> str:
    """Export a printable report (PDF/XLSX) for a record, or the whole
    evidence listing, to a local file.

    Does not modify AbraFlexi data; only writes ``output_path`` on the MCP host.

    Args:
        evidence: Evidence name
        output_path: Local filesystem path to write the exported report to
        id: Record ID to export a report for; the whole evidence listing is
            exported if both id and kod are omitted
        kod: Record code (alternative to id)
        report_format: "pdf" or "xls"
        report_name: Specific report identifier (see evidence_get_reports)
        report_lang: Report language ("cs", "sk", "en" or "de")
        report_sign: Whether to electronically sign the exported PDF

    Returns:
        str: JSON formatted result with the written file path and size
    """
    record_id: Optional[Union[int, str]] = None
    if id:
        record_id = int(id)
    elif kod:
        record_id = f"code:{kod}"

    # export_report lives on ReadWrite in python-abraflexi; the HTTP call is GET.
    client = get_readwrite_client(evidence)
    content = client.export_report(
        record_id=record_id,
        report_format=report_format,
        report_name=report_name,
        report_lang=report_lang,
        report_sign=report_sign,
    )
    if not content:
        raise ValueError("Report export failed or returned no data")

    with open(output_path, "wb") as fh:
        fh.write(content)

    return format_response({"success": True, "path": output_path, "size_bytes": len(content)})


@mcp.tool(annotations=_RO_ANN)
def evidence_get_qr_code(
    evidence: str,
    id: Optional[str] = None,
    kod: Optional[str] = None,
    size: int = 140,
    output_path: Optional[str] = None
) -> str:
    """Get the payment QR code for a document record.

    Does not modify AbraFlexi data. Optionally writes a local PNG when
    ``output_path`` is set; otherwise returns a base64 data URI.

    Args:
        evidence: Evidence name (e.g., 'faktura-vydana')
        id: Record ID
        kod: Record code (alternative to id)
        size: Requested image size in pixels
        output_path: If given, write the PNG to this local path instead of
            returning it inline as a base64 data URI

    Returns:
        str: JSON formatted result - either the written file path, or a
            base64 data URI
    """
    identifier = _require_record_identifier(id, kod)
    # QR helpers live on ReadWrite in python-abraflexi; the HTTP call is GET.
    client = get_readwrite_client(evidence)

    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    if output_path:
        content = client.get_qr_code_image(size)
        if not content:
            raise ValueError("QR code export failed or returned no data")
        with open(output_path, "wb") as fh:
            fh.write(content)
        return format_response({"success": True, "path": output_path, "size_bytes": len(content)})

    data_uri = client.get_qr_code_base64(size)
    return format_response({"success": bool(data_uri), "data_uri": data_uri})


@mcp.tool(annotations=_RO_ANN)
def user_query_list(
    limit: Optional[int] = None,
    detail: str = "custom:id,kod,nazev",
) -> str:
    """List saved user-defined queries (uzivatelsky-dotaz) on the bound company.

    Args:
        limit: Maximum number of queries to return
        detail: AbraFlexi detail level (default returns id/kod/nazev)

    Returns:
        str: JSON object with ``_context`` and ``records``
    """
    client = get_readonly_client("uzivatelsky-dotaz")
    client.default_url_params["detail"] = detail
    if limit:
        client.default_url_params["limit"] = limit
    result = client.get_all_from_abraflexi()
    return format_records_response(
        result,
        record_note=(
            "These are saved user queries (uzivatelsky-dotaz) belonging to the "
            "bound company. Pass a record's id or kod to call_user_query."
        ),
    )


@mcp.tool(annotations=_RO_ANN)
def call_user_query(
    query_id: str,
    params: Optional[Dict[str, Any]] = None,
    method: str = "GET"
) -> str:
    """Call a saved user-defined query (uzivatelsky dotaz).

    Args:
        query_id: Identifier of the saved query (id or code from user_query_list)
        params: Query parameters; a list value repeats the parameter in the
            URL, matching AbraFlexi's N-arity query parameter syntax
        method: HTTP method to use (GET or POST)

    Returns:
        str: JSON formatted query result rows
    """
    config = get_abraflexi_config()
    client = ReadOnly(None, config)
    result = client.call_user_query(query_id, params=params, method=method)
    return format_response(result)


# EVIDENCE METADATA & SUMMATION
@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_get_properties(evidence: str) -> str:
    """Get the list of properties (fields) supported by an evidence.

    Args:
        evidence: Evidence name

    Returns:
        str: JSON formatted list of properties
    """
    client = get_readonly_client(evidence)
    result = client.get_properties()
    return format_response(result)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_get_reports(evidence: str) -> str:
    """Get the list of printable reports available for an evidence.

    Args:
        evidence: Evidence name

    Returns:
        str: JSON formatted list of reports
    """
    client = get_readonly_client(evidence)
    result = client.get_reports()
    return format_response(result)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_get_relations_list(evidence: str) -> str:
    """Get the list of sub-evidences (relations) available for an evidence.

    Args:
        evidence: Evidence name

    Returns:
        str: JSON formatted list of relations
    """
    client = get_readonly_client(evidence)
    result = client.get_relations_list()
    return format_response(result)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_get_sum(
    evidence: str,
    filter_expr: Optional[str] = None,
    conditions: Optional[Dict[str, Any]] = None
) -> str:
    """Get summation (totals) for an evidence, optionally filtered.

    Args:
        evidence: Evidence name
        filter_expr: AbraFlexi filter expression to scope the summation
        conditions: Additional URL parameters to apply to the request

    Returns:
        str: JSON formatted summation result
    """
    client = get_readonly_client(evidence)
    if filter_expr:
        client.filter = filter_expr
    result = client.get_sum(conditions)
    return format_response(result)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_get_record_changes(evidence: str, id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Get the change history (Prehled zmen zaznamu) of a single record.

    Args:
        evidence: Evidence name
        id: Record ID
        kod: Record code (alternative to id)

    Returns:
        str: JSON formatted list of change entries
    """
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = str(id) if id else f"code:{kod}"
    client = get_readonly_client(evidence)
    result = client.perform_request(f"{identifier}/zmeny.json")

    return format_response(result)


# LABELS (stitky)
@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_get_labels(evidence: str, id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Get all labels (stitky) currently assigned to a record.

    Args:
        evidence: Evidence name
        id: Record ID
        kod: Record code (alternative to id)

    Returns:
        str: JSON formatted list of label codes
    """
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    client = get_readonly_client(evidence)

    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    labels_value = client.get_data_value("stitky")
    labels = [label.strip() for label in str(labels_value or "").split(",") if label.strip()]

    return format_response(labels)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_set_label(evidence: str, label: str, id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Add a label to a record, keeping its existing labels.

    Args:
        evidence: Evidence name
        label: Label code to assign (e.g. 'code:VIP')
        id: Record ID
        kod: Record code (alternative to id)

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client(evidence)

    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    client.insert_to_abraflexi({"id": client.get_record_ident(), "stitky": label})

    return format_response({"success": client.last_response_code == 201})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_unset_label(
    evidence: str,
    labels_to_remove: List[str],
    id: Optional[str] = None,
    kod: Optional[str] = None
) -> str:
    """Remove specific label(s) from a record, keeping the rest.

    Args:
        evidence: Evidence name
        labels_to_remove: Label code(s) to remove
        id: Record ID
        kod: Record code (alternative to id)

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client(evidence)

    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    to_remove = set(labels_to_remove)
    current = str(client.get_data_value("stitky") or "").split(",")
    remaining = [label.strip() for label in current if label.strip() and label.strip() not in to_remove]

    client.insert_to_abraflexi(
        {"id": client.get_record_ident(), "stitky@removeAll": "true", "stitky": remaining}
    )

    return format_response({"success": client.last_response_code == 201})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def evidence_unset_labels(evidence: str, id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Remove all labels from a record.

    Args:
        evidence: Evidence name
        id: Record ID
        kod: Record code (alternative to id)

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    client = get_readwrite_client(evidence)

    if not client.load_from_abraflexi(identifier):
        raise ValueError(f"Record not found in {evidence}: {identifier}")

    client.insert_to_abraflexi({"id": client.get_record_ident(), "stitky@removeAll": "true"})

    return format_response({"success": client.last_response_code == 201})


# CHANGES API (company-wide incremental sync)
@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def changes_enable() -> str:
    """Enable change tracking for the current company (Changes API).

    Returns:
        str: JSON formatted result
    """
    validate_read_only()
    config = get_abraflexi_config()
    client = Changes(None, config)
    result = client.enable()
    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def changes_disable() -> str:
    """Disable change tracking for the current company (Changes API).

    Returns:
        str: JSON formatted result
    """
    validate_read_only()
    config = get_abraflexi_config()
    client = Changes(None, config)
    result = client.disable()
    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def changes_status() -> str:
    """Check whether change tracking is currently enabled for the current company.

    Returns:
        str: JSON formatted status
    """
    config = get_abraflexi_config()
    client = Changes(None, config)
    result = client.get_status()
    return format_response({"enabled": result})


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def changes_get(
    start: Optional[int] = None,
    limit: Optional[int] = None,
    evidences: Optional[List[str]] = None
) -> str:
    """Get a page of company-wide recorded changes (Changes API), for
    incremental synchronization of external systems.

    Changes are scoped to the AbraFlexi company this server is bound to
    (see server_info).

    Args:
        start: Global version to start listing from (inclusive); defaults to
            the beginning of tracked history
        limit: Maximum number of changes to return (server default 100, max 1000)
        evidences: Restrict the listing to these evidence names

    Returns:
        str: JSON object with a _context block (bound company/URL) and a
            records page containing 'changes', 'next' and 'global_version'
    """
    config = get_abraflexi_config()
    client = Changes(None, config)
    result = client.get_changes(start=start, limit=limit, evidences=evidences)
    return format_records_response(
        result,
        record_note=(
            "This change page belongs to the AbraFlexi company this server "
            "is bound to (see abraflexi_company above / server_info tool)."
        ),
    )


# ISSUED INVOICE BUSINESS LOGIC (FakturaVydana)
@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def invoice_issued_match_payment(
    payment_id: str,
    id: Optional[str] = None,
    kod: Optional[str] = None,
    payment_evidence: str = "banka",
    zbytek: str = "ignorovat",
    overpay_to: str = ""
) -> str:
    """Match an issued invoice against a payment document (Parovani plateb).

    Args:
        payment_id: ID (or 'code:X') of the paying document
        id: Invoice ID
        kod: Invoice code (alternative to id)
        payment_evidence: Evidence of the paying document ('banka',
            'interni-doklad' or 'pokladni-pohyb')
        zbytek: How to handle any remainder - one of ne|zauctovat|ignorovat|
            castecnaUhrada|castecnaUhradaNeboZauctovat|castecnaUhradaNeboIgnorovat
        overpay_to: Document type code to use for an overpayment, if any

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    invoice = get_faktura_vydana_client(identifier)

    payment = get_readwrite_client(payment_evidence)
    payment.my_key = int(payment_id) if payment_id.isdigit() else payment_id

    result = invoice.match_payment(payment, zbytek=zbytek, overpay_to=overpay_to)

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def invoice_issued_cash_payment(
    value: float,
    id: Optional[str] = None,
    kod: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None
) -> str:
    """Pay an issued invoice in cash (Hotovostni uhrada).

    Args:
        value: Amount to pay
        id: Invoice ID
        kod: Invoice code (alternative to id)
        extra_fields: Optional payment properties: 'pokladna' (cash register
            code, default 'code:POKLADNA KC'), 'typDokl' (cash document type
            code, default 'code:STANDARD'), 'kurzKDatuUhrady' (bool),
            'datumUhrady' (default today)

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    invoice = get_faktura_vydana_client(identifier)

    result = invoice.cash_payment(value, **(extra_fields or {}))

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def invoice_issued_deduct_advance(
    advance_invoice_id: str,
    id: Optional[str] = None,
    kod: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None
) -> str:
    """Deduct an advance invoice from a tax document invoice (Odpocet zaloh a ZDD).

    Args:
        advance_invoice_id: ID (or 'code:X') of the advance ('zalohova') invoice being deducted
        id: Invoice ID
        kod: Invoice code (alternative to id)
        extra_fields: Deduction properties; 'castkaMen' defaults to the
            advance invoice's total

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    invoice = get_faktura_vydana_client(identifier)
    advance = get_faktura_vydana_client(
        int(advance_invoice_id) if advance_invoice_id.isdigit() else advance_invoice_id
    )

    result = invoice.deduct_advance(advance, **(extra_fields or {}))

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def invoice_issued_deduct_zdd(
    zdd_invoice_id: str,
    id: Optional[str] = None,
    kod: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None
) -> str:
    """Deduct an advance tax document (ZDD) from an issued invoice (Odpocet zaloh a ZDD).

    Args:
        zdd_invoice_id: ID (or 'code:X') of the ZDD invoice being deducted
        id: Invoice ID
        kod: Invoice code (alternative to id)
        extra_fields: Deduction properties; the 'castka*Men' fields default
            to the ZDD invoice's corresponding totals

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    invoice = get_faktura_vydana_client(identifier)
    zdd = get_faktura_vydana_client(
        int(zdd_invoice_id) if zdd_invoice_id.isdigit() else zdd_invoice_id
    )

    result = invoice.deduct_zdd(zdd, **(extra_fields or {}))

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def invoice_issued_link_zdd(
    income_id: str,
    id: Optional[str] = None,
    kod: Optional[str] = None,
    income_evidence: str = "banka"
) -> str:
    """Link an advance tax document (ZDD) to an income payment (Vazby ZDD).

    Args:
        income_id: ID (or 'code:X') of the income payment document
        id: Invoice ID
        kod: Invoice code (alternative to id)
        income_evidence: Evidence of the income payment document ('banka' or 'pokladni-pohyb')

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    invoice = get_faktura_vydana_client(identifier)

    income = get_readwrite_client(income_evidence)
    income.my_key = int(income_id) if income_id.isdigit() else income_id

    result = invoice.link_zdd(income)

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True})
def invoice_issued_unlink_zdd(id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Remove an advance tax document (ZDD) bonding from an issued invoice (Vazby ZDD).

    Args:
        id: Invoice ID
        kod: Invoice code (alternative to id)

    Returns:
        str: JSON formatted result
    """
    validate_read_only()

    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    invoice = get_faktura_vydana_client(identifier)

    result = invoice.unlink_zdd()

    return format_response({"success": result})


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
def invoice_issued_overdue_days(due_date: str) -> str:
    """Get the number of days an invoice is overdue by, given its due date.
    Pure date arithmetic - does not contact AbraFlexi.

    Args:
        due_date: Due date as an ISO 'YYYY-MM-DD' string

    Returns:
        str: JSON formatted result with the (possibly negative) number of overdue days
    """
    days = FakturaVydana.overdue_days(due_date)
    return format_response({"overdue_days": days})


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def invoice_issued_get_email(id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Get the best recipient email address for an issued invoice.

    Args:
        id: Invoice ID
        kod: Invoice code (alternative to id)

    Returns:
        str: JSON formatted result with the resolved email address
    """
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    invoice = get_faktura_vydana_client(identifier)

    return format_response({"email": invoice.get_email()})


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def invoice_issued_get_recipients(
    id: Optional[str] = None,
    kod: Optional[str] = None,
    purpose: str = ""
) -> str:
    """Get all recipient email addresses for an issued invoice.

    Args:
        id: Invoice ID
        kod: Invoice code (alternative to id)
        purpose: Contact purpose (Fak|Obj|Nab|Ppt|Skl|Pok); auto-detected if omitted

    Returns:
        str: JSON formatted result with a comma-separated list of email addresses
    """
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    invoice = get_faktura_vydana_client(identifier)

    return format_response({"recipients": invoice.get_recipients(purpose)})


# CONTACT CONVENIENCE LOOKUPS (Adresar)
@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def contact_get_notification_email(
    id: Optional[str] = None,
    kod: Optional[str] = None,
    purpose: str = ""
) -> str:
    """Get the email address to notify for a contact, preferring a primary/
    purpose-matching contact over the address's own email.

    Args:
        id: Contact ID
        kod: Contact code (alternative to id)
        purpose: Contact purpose - one of Fak|Obj|Nab|Ppt|Skl|Pok

    Returns:
        str: JSON formatted result with the resolved email address
    """
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    contact = get_adresar_client(identifier)

    return format_response({"email": contact.get_notification_email_address(purpose)})


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def contact_get_cell_phone(
    id: Optional[str] = None,
    kod: Optional[str] = None,
    purpose: str = ""
) -> str:
    """Get the cell phone number to use for a contact.

    Args:
        id: Contact ID
        kod: Contact code (alternative to id)
        purpose: Contact purpose - one of Fak|Obj|Nab|Ppt|Skl|Pok

    Returns:
        str: JSON formatted result with the resolved phone number
    """
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    contact = get_adresar_client(identifier)

    return format_response({"cell_phone": contact.get_cell_phone_number(purpose)})


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def contact_get_any_phone(
    id: Optional[str] = None,
    kod: Optional[str] = None,
    purpose: str = ""
) -> str:
    """Get any usable phone number for a contact, preferring mobile over landline.

    Args:
        id: Contact ID
        kod: Contact code (alternative to id)
        purpose: Contact purpose - one of Fak|Obj|Nab|Ppt|Skl|Pok

    Returns:
        str: JSON formatted result with the resolved phone number
    """
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    contact = get_adresar_client(identifier)

    return format_response({"phone": contact.get_any_phone_number(purpose)})


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
def contact_get_bank_accounts(id: Optional[str] = None, kod: Optional[str] = None) -> str:
    """Get the bank account(s) registered for a contact.

    Args:
        id: Contact ID
        kod: Contact code (alternative to id)

    Returns:
        str: JSON formatted list of bank accounts (buc, smerKod)
    """
    if not id and not kod:
        raise ValueError("Either id or kod must be provided")

    identifier = int(id) if id else f"code:{kod}"
    contact = get_adresar_client(identifier)

    return format_response(contact.get_bank_account_number())


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
def abraflexi_client_methods(client_class: Optional[str] = None, include_signatures: bool = True) -> str:
    """List public python-abraflexi methods available via bridge calls.

    Args:
        client_class: Optional class name to narrow results
            (ReadOnly, ReadWrite, Changes, Adresar, FakturaVydana)
        include_signatures: Include Python signatures and one-line docs

    Returns:
        str: JSON formatted list of methods grouped by class
    """
    if client_class and client_class not in CLIENT_CLASS_MAP:
        raise ValueError(
            f"Unsupported client_class '{client_class}'. Supported: {', '.join(CLIENT_CLASS_MAP.keys())}"
        )

    classes = [client_class] if client_class else list(CLIENT_CLASS_MAP.keys())
    result: Dict[str, Any] = {}

    for class_name in classes:
        cls = CLIENT_CLASS_MAP[class_name]
        methods = _public_methods_for_class(cls)
        if not include_signatures:
            result[class_name] = methods
            continue

        detailed = []
        for method_name in methods:
            fn = getattr(cls, method_name)
            try:
                signature = str(inspect.signature(fn))
            except Exception:
                signature = "(signature unavailable)"
            doc = (inspect.getdoc(fn) or "").splitlines()
            doc_first_line = doc[0] if doc else ""
            detailed.append({
                "name": method_name,
                "signature": signature,
                "doc": doc_first_line,
                "write_method": method_name in WRITE_METHOD_NAMES,
            })
        result[class_name] = detailed

    return format_response(result)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
def abraflexi_client_call(
    client_class: str,
    method: str,
    init: Optional[Union[int, str, Dict[str, Any]]] = None,
    evidence: Optional[str] = None,
    company: Optional[str] = None,
    method_args: Optional[List[Any]] = None,
    method_kwargs: Optional[Dict[str, Any]] = None,
    extra_options: Optional[Dict[str, Any]] = None,
) -> str:
    """Call a public python-abraflexi client method through MCP.

    This bridge tool is intended for advanced workflows not yet covered by
    dedicated MCP wrappers.

    Args:
        client_class: One of ReadOnly, ReadWrite, Changes, Adresar, FakturaVydana
        method: Public method name on the selected client class
        init: Optional record selector or initial data passed to constructor
        evidence: Evidence name (used mainly with ReadOnly/ReadWrite)
        company: Optional company override (dbNazev)
        method_args: Positional arguments for the method call
        method_kwargs: Keyword arguments for the method call
        extra_options: Additional constructor options for the client

    Returns:
        str: JSON formatted result and runtime metadata
    """
    if method.startswith("_"):
        raise ValueError("Private methods are not allowed")

    client = _instantiate_client(
        client_class=client_class,
        init=init,
        evidence=evidence,
        company=company,
        extra_options=extra_options,
    )

    if not hasattr(client, method):
        raise ValueError(f"Method '{method}' not found on {client_class}")

    fn = getattr(client, method)
    if not callable(fn):
        raise ValueError(f"Attribute '{method}' on {client_class} is not callable")

    if method in WRITE_METHOD_NAMES:
        validate_read_only()

    args = method_args or []
    kwargs = method_kwargs or {}
    result = fn(*args, **kwargs)

    return format_response({
        "client_class": client_class,
        "method": method,
        "result": _serialize_result(result),
        "last_response_code": getattr(client, "last_response_code", None),
        "row_count": getattr(client, "row_count", None),
        "global_version": getattr(client, "global_version", None),
        "errors": getattr(client, "errors", None),
    })


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
def evidence_list() -> str:
    """List all evidences available on the bound AbraFlexi company.

    Fetches ``/c/{company}/evidence-list.json`` so the result matches the
    live instance (typically 200+ evidences), not a hardcoded subset.

    Returns:
        str: JSON object with ``count`` and ``evidences`` (each entry has
            at least ``name`` / ``evidencePath`` and ``description`` /
            ``evidenceName`` when the API provides them).
    """
    # evidence=None → company-level URL; suffix hits evidence-list.json
    config = get_abraflexi_config()
    client = ReadOnly(None, {**config, "evidence": None})
    raw = client.perform_request(url_suffix="evidence-list.json")

    evidences: List[Dict[str, Any]] = []
    if isinstance(raw, dict):
        # AbraFlexi wraps as {"evidences": {"evidence": [...]}} or similar
        block = raw.get("evidences") or raw.get("winstrom") or raw
        if isinstance(block, dict):
            items = block.get("evidence") or block.get("evidences") or []
        else:
            items = block
        if isinstance(items, dict):
            items = [items]
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                path = item.get("evidencePath") or item.get("name")
                if not path:
                    continue
                evidences.append(
                    {
                        "name": path,
                        "description": item.get("evidenceName")
                        or item.get("evidenceType")
                        or item.get("description"),
                        "evidenceType": item.get("evidenceType"),
                        "dbName": item.get("dbName"),
                        "extIdSupported": item.get("extIdSupported"),
                        "importStatus": item.get("importStatus"),
                    }
                )

    if not evidences:
        raise ValueError(
            "Could not load evidence-list from AbraFlexi "
            f"(response type={type(raw).__name__})"
        )

    evidences.sort(key=lambda e: str(e.get("name") or ""))
    return format_response({"count": len(evidences), "evidences": evidences})


def main():
    """Main entry point for the MCP server."""
    parser = argparse.ArgumentParser(
        prog="abraflexi-mcp",
        description=(
            "MCP server for AbraFlexi integration (invoices, contacts, "
            "products, bank transactions, generic evidence)."
        ),
        epilog=(
            "Configuration is read from environment variables or a .env "
            "file (see .env.example):\n"
            "  ABRAFLEXI_URL, ABRAFLEXI_COMPANY, ABRAFLEXI_LOGIN, ABRAFLEXI_PASSWORD\n"
            "  READ_ONLY, ABRAFLEXI_MCP_TRANSPORT (stdio|streamable-http),\n"
            "  ABRAFLEXI_MCP_HOST, ABRAFLEXI_MCP_PORT, ABRAFLEXI_MCP_STATELESS_HTTP"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.parse_args()

    # Get transport configuration
    transport = os.getenv("ABRAFLEXI_MCP_TRANSPORT", "stdio").lower()
    
    if transport == "streamable-http":
        # HTTP transport configuration
        host = os.getenv("ABRAFLEXI_MCP_HOST", "127.0.0.1")
        port = int(os.getenv("ABRAFLEXI_MCP_PORT", "8000"))
        stateless = os.getenv("ABRAFLEXI_MCP_STATELESS_HTTP", "false").lower() in ("true", "1", "yes")
        
        logger.info(f"Starting MCP server with HTTP transport on {host}:{port}")
        mcp.run(transport="streamable-http", host=host, port=port, stateless=stateless)
    else:
        # Default stdio transport
        logger.info("Starting MCP server with stdio transport")
        mcp.run()


if __name__ == "__main__":
    main()
