# AbraFlexi MCP Server

<img src="debian/abraflexi-mcp-server.svg" alt="AbraFlexi MCP Server icon" width="96" height="96">

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://badge.fury.io/py/abraflexi-mcp-server.svg)](https://badge.fury.io/py/abraflexi-mcp-server)
![Packaging: deb](https://img.shields.io/badge/packaging-.deb-red?logo=debian&logoColor=white)
[![M8ven Score](https://m8ven.ai/badge/mcp/vitexsoftware-abraflexi-mcp-server-jhy0dc)](https://m8ven.ai/mcp/vitexsoftware-abraflexi-mcp-server-jhy0dc)

A comprehensive Model Context Protocol (MCP) server for AbraFlexi integration using FastMCP and python-abraflexi. This server provides complete access to AbraFlexi REST API functionality through MCP-compatible tools.

## Features

68 tools in total, covering the full REST surface exposed by
[python-abraflexi](https://github.com/VitexSoftware/python-abraflexi):
dedicated tools for the most common evidences (invoices, contacts,
products, bank transactions), plus generic `evidence_*` tools that work
against *any* AbraFlexi evidence by name.

> **One server process = one AbraFlexi company.** A running server is bound
> for its whole lifetime to a single company, set via
> `ABRAFLEXI_URL`/`ABRAFLEXI_COMPANY` (see [Configuration](#configuration)).
> Every record any tool returns already belongs to that company - it is not
> possible to ask this server for another company's data. Call `server_info`
> to check which company/URL a running server is bound to; the main
> record-fetching tools (`invoice_issued_get`, `invoice_received_get`,
> `contact_get`, `product_get`, `bank_transaction_get`, `evidence_get`,
> `changes_get`) also echo it back in a `_context` block on every response,
> together with a note clarifying any counterparty fields on the records
> (e.g. an invoice's `nazFirmy` is the customer/supplier, not the company
> that issued/received it).

### ℹ️ Server Identity
- `server_info` - Report which AbraFlexi company/URL this server session is bound to

### 📄 Invoice Management
- `invoice_issued_get` - Retrieve issued invoices (faktura-vydana)
- `invoice_issued_create` - Create new issued invoices
- `invoice_issued_update` - Update existing issued invoices
- `invoice_issued_delete` - Remove issued invoices
- `invoice_received_get` - Retrieve received invoices (faktura-prijata)
- `invoice_received_create` - Create new received invoices

### 💳 Issued Invoice Business Logic
- `invoice_issued_match_payment` - Match an invoice against a payment document (Párování plateb)
- `invoice_issued_cash_payment` - Pay an invoice in cash (Hotovostní úhrada)
- `invoice_issued_deduct_advance` - Deduct an advance invoice (Odpočet záloh a ZDD)
- `invoice_issued_deduct_zdd` - Deduct an advance tax document, ZDD (Odpočet záloh a ZDD)
- `invoice_issued_link_zdd` - Link a ZDD to an income payment (Vazby ZDD)
- `invoice_issued_unlink_zdd` - Remove a ZDD bonding (Vazby ZDD)
- `invoice_issued_overdue_days` - Compute days overdue from a due date (pure, no API call)
- `invoice_issued_get_email` - Resolve the best recipient email for an invoice
- `invoice_issued_get_recipients` - Resolve all recipient emails for an invoice

### 🏢 Company Management
- `company_create` - Found a brand-new AbraFlexi company (accounting unit) - requires server-admin/license REST rights

### 👥 Contact Management
- `contact_get` - Retrieve contacts and companies (adresar)
- `contact_create` - Create new contacts
- `contact_update` - Update existing contacts
- `contact_delete` - Remove contacts

### ☎️ Contact Convenience Lookups
- `contact_get_notification_email` - Best email to notify (primary/purpose-matching contact)
- `contact_get_cell_phone` - Cell phone number to use
- `contact_get_any_phone` - Any usable phone number (mobile preferred over landline)
- `contact_get_bank_accounts` - Registered bank account(s) for a contact

### 📦 Product Management
- `product_get` - Retrieve products from price list (cenik)
- `product_create` - Create new products
- `product_update` - Update existing products
- `product_delete` - Remove products

### 🏦 Bank Transaction Management
- `bank_transaction_get` - Retrieve bank transactions (banka)
- `bank_transaction_create` - Create new bank transactions

### 🔧 Generic Evidence Operations
- `evidence_get` - Get records from any evidence (filter, pagination, sorting, relations)
- `evidence_create` - Create record in any evidence
- `evidence_update` - Update record in any evidence (supports `remove_external_ids`)
- `evidence_delete` - Delete record from any evidence
- `evidence_list` - List all evidences available on the bound company (live `evidence-list.json`)

### 🧠 Python-abraflexi Bridge
- `abraflexi_client_methods` - List public methods of core python-abraflexi clients (`ReadOnly`, `ReadWrite`, `Changes`, `Adresar`, `FakturaVydana`)
- `abraflexi_client_call` - Invoke a selected public client method with arguments (write methods still respect `READ_ONLY`)

### 🔒 Locking, Actions & Batch Operations
- `evidence_lock` / `evidence_unlock` / `evidence_lock_for_ucetni` - Lock/unlock a record
- `evidence_storno` - Cancel (storno) a document record
- `evidence_perform_action` - Call a record's dedicated business action (e.g. `pay`)
- `evidence_mass_update` - Update, or act on, every record matching a filter (Dávkové operace)
- `evidence_batch_insert` / `evidence_batch_update` - Insert/update many records in one request

### 📎 Attachments
- `evidence_attach_file` - Attach a local file to any record
- `evidence_list_attachments` - List a record's attachments
- `evidence_get_attachment` - Get metadata for a single attachment
- `evidence_download_attachment` - Download an attachment to a local file
- `evidence_get_attachment_thumbnail` - Download an image attachment's thumbnail
- `evidence_delete_attachment` - Delete an attachment

### 🧾 Reports, QR Codes & User Queries
- `evidence_export_report` - Export a PDF/XLSX report for a record or evidence listing
- `evidence_get_qr_code` - Get a document's payment QR code (file or base64 data URI)
- `call_user_query` - Call a saved user-defined query (uživatelský dotaz)

### ℹ️ Evidence Metadata & Summation
- `evidence_get_properties` - List the fields supported by an evidence
- `evidence_get_reports` - List the printable reports available for an evidence
- `evidence_get_relations_list` - List the sub-evidences (relations) available for an evidence
- `evidence_get_sum` - Get summation (totals) for an evidence
- `evidence_get_record_changes` - Get a single record's change history

### 🏷️ Labels (štítky)
- `evidence_get_labels` - Get labels assigned to a record
- `evidence_set_label` - Add a label
- `evidence_unset_label` - Remove specific label(s)
- `evidence_unset_labels` - Remove all labels

### 🔄 Changes API (company-wide incremental sync)
- `changes_enable` / `changes_disable` - Toggle change tracking
- `changes_status` - Check whether change tracking is enabled
- `changes_get` - Page through recorded changes since a given version

## Installation

### Prerequisites

- Python 3.10 or higher
- Access to an AbraFlexi server with API enabled

### Option 1: Install from PyPI (Recommended)

```bash
pip install abraflexi-mcp-server
```

Then run the server:
```bash
abraflexi-mcp
```

### Option 2: AppImage (Linux)

Download the self-contained AppImage from the
[latest release](https://github.com/VitexSoftware/abraflexi-mcp-server/releases/latest):

```bash
chmod +x AbraFlexi-MCP-Server-*-x86_64.AppImage
./AbraFlexi-MCP-Server-*-x86_64.AppImage
```

No Python or pip required. See [AppImage](#appimage) section for details.

### Option 3: Install from Source

1. **Clone the repository:**
   ```bash
   git clone https://github.com/VitexSoftware/abraflexi-mcp-server.git
   cd abraflexi-mcp-server
   ```

2. **Install with uv (recommended):**
   ```bash
   uv sync
   uv run python scripts/start_server.py
   ```
   
   Or with pip:
   ```bash
   pip install -e .
   abraflexi-mcp
   ```

## Cloud Deployment

A testing deployment is available at:

**🌐 https://abraflexi.fastmcp.app/mcp**

This cloud-hosted instance allows you to test and use the AbraFlexi MCP server without local installation. Configure your MCP client to connect to this endpoint with HTTP transport.

**Note:** This is a testing deployment. For production use, we recommend self-hosting using one of the installation methods above.

### Configuration

Create a `.env` file or set environment variables:
```bash
cp .env.example .env
# Edit .env with your AbraFlexi server details
```

## Configuration

### Required Environment Variables

- `ABRAFLEXI_URL` - Your AbraFlexi server URL (e.g., `https://demo.flexibee.eu:5434`)
- `ABRAFLEXI_COMPANY` - Company identifier (e.g., `demo_de`)

### Authentication (choose one method)

**Method 1: Username/Password (Recommended)**
- `ABRAFLEXI_LOGIN` - Your AbraFlexi username
- `ABRAFLEXI_PASSWORD` - Your AbraFlexi password

**Method 2: Session ID**
- `ABRAFLEXI_AUTHSESSID` - Your AbraFlexi session ID

### Optional Configuration

- `READ_ONLY` - Set to `true`, `1`, or `yes` to enable read-only mode (default: `true`)
- `ABRAFLEXI_TIMEOUT` - Request timeout in seconds (default: `300`)

### Transport Configuration

- `ABRAFLEXI_MCP_TRANSPORT` - Transport type: `stdio` (default) or `streamable-http`

**HTTP Transport Configuration** (only used when `ABRAFLEXI_MCP_TRANSPORT=streamable-http`):
- `ABRAFLEXI_MCP_HOST` - Server host (default: `127.0.0.1`)
- `ABRAFLEXI_MCP_PORT` - Server port (default: `8000`)
- `ABRAFLEXI_MCP_STATELESS_HTTP` - Stateless mode (default: `false`)
- `AUTH_TYPE` - Must be set to `no-auth` for streamable-http transport

## Usage

### Running the Server

**With startup script (recommended):**
```bash
uv run python scripts/start_server.py
```

**Direct execution:**
```bash
uv run python -m abraflexi_mcp_server.server
```

**CLI help:**
```bash
abraflexi-mcp --help
```

### Transport Options

The server supports two transport methods:

#### STDIO Transport (Default)
Standard input/output transport for MCP clients like Claude Desktop:
```bash
# Set in .env or environment
ABRAFLEXI_MCP_TRANSPORT=stdio
```

#### HTTP Transport
HTTP-based transport for web integrations:
```bash
# Set in .env or environment
ABRAFLEXI_MCP_TRANSPORT=streamable-http
ABRAFLEXI_MCP_HOST=127.0.0.1
ABRAFLEXI_MCP_PORT=8000
ABRAFLEXI_MCP_STATELESS_HTTP=false
AUTH_TYPE=no-auth
```

### Testing

**Run test suite:**
```bash
uv run python scripts/test_server.py
```

### Read-Only Mode

When `READ_ONLY=true` (default), the server will only expose GET operations (retrieve data) and block all create, update, and delete operations. This is useful for:

- 📊 Monitoring dashboards
- 🔍 Read-only integrations
- 🔒 Security-conscious environments
- 🛡️ Preventing accidental modifications

To enable write operations, set `READ_ONLY=false` in your `.env` file.

### Example Tool Calls

**Get all issued invoices:**
```python
invoice_issued_get(limit=10)
```

**Get specific invoice by code:**
```python
invoice_issued_get(kod="INV-2024-001")
```

**Count invoices issued in August 2026 (without downloading full records):**
```python
invoice_issued_get(
    datum_vystaveni_od="2026-08-01",
    datum_vystaveni_do="2026-08-31",
    detail="id",
    add_row_count=True
)
```

**Create a new contact:**
```python
contact_create(
    kod="CUSTOMER01",
    nazev="Example Company s.r.o.",
    email="info@example.com",
    tel="+420123456789"
)
```

**Get products:**
```python
product_get(nazev="Widget", limit=5)
```

**Generic evidence query (with pagination/sorting):**
```python
evidence_get(
    evidence="faktura-vydana",
    filter_expr="datVyst >= '2024-01-01'",
    order="datVyst",
    order_direction="D",
    limit=20,
    start=0
)
```

**Attach a local file to any record:**
```python
evidence_attach_file(evidence="cenik", kod="PRODUCT01", filepath="/path/to/photo.jpg")
```

**Lock an invoice, then export its PDF:**
```python
evidence_lock(evidence="faktura-vydana", kod="INV-2024-001")
evidence_export_report(
    evidence="faktura-vydana",
    kod="INV-2024-001",
    output_path="/tmp/invoice.pdf",
    report_name="dodaciList"
)
```

**Mass-update every price-list item from a supplier:**
```python
evidence_mass_update(
    evidence="cenik",
    filter_expr="dodavatel = 'code:SUPPLIER01'",
    data={"stitky": "code:VIP"}
)
```

**Incremental sync via the Changes API:**
```python
changes_enable()
page = changes_get(start=0, limit=500, evidences=["faktura-vydana"])
# page["changes"], page["next"], page["global_version"]
```

## MCP Integration

This server is designed to work with MCP-compatible clients like Claude Desktop. See [MCP_SETUP.md](MCP_SETUP.md) for detailed integration instructions.

## OCI Container

The server can be run as an OCI container (Docker/Podman) — no Python installation needed on the host.

### Building the image

```bash
podman build -t abraflexi-mcp-server -f Containerfile .
```

### Running the container

The image defaults to `streamable-http` transport on port **8000**.

**With individual environment variables:**
```bash
podman run --rm -p 8000:8000 \
  -e ABRAFLEXI_URL=https://demo.flexibee.eu:5434 \
  -e ABRAFLEXI_COMPANY=demo_de \
  -e ABRAFLEXI_LOGIN=winstrom \
  -e ABRAFLEXI_PASSWORD=winstrom \
  abraflexi-mcp-server
```

**With an env file:**
```bash
podman run --rm -p 8000:8000 --env-file .env abraflexi-mcp-server
```

### Container environment defaults

| Variable | Default |
|---|---|
| `ABRAFLEXI_MCP_TRANSPORT` | `streamable-http` |
| `ABRAFLEXI_MCP_HOST` | `0.0.0.0` |
| `ABRAFLEXI_MCP_PORT` | `8000` |
| `READ_ONLY` | `true` |

All other [configuration variables](#configuration) can be passed as environment variables.

## AppImage

A self-contained, single-file Linux executable — no Python, pip, or any other dependency required on the host.

### Building the AppImage

```bash
bash appimage/build-appimage.sh
```

The script downloads a portable CPython and `appimagetool` automatically. The resulting file is placed in `build/appimage/`:

```
build/appimage/AbraFlexi-MCP-Server-<version>-x86_64.AppImage
```

### Running the AppImage

The AppImage automatically loads a `.env` file from the current working directory if one is present.

**With a .env file (recommended):**
```bash
cp .env.example .env
# edit .env with your credentials
./AbraFlexi-MCP-Server-*-x86_64.AppImage
```

**With inline environment variables:**
```bash
ABRAFLEXI_URL=https://demo.flexibee.eu:5434 \
ABRAFLEXI_COMPANY=demo_de \
ABRAFLEXI_LOGIN=winstrom \
ABRAFLEXI_PASSWORD=winstrom \
./AbraFlexi-MCP-Server-*-x86_64.AppImage
```

## Development

### Project Structure

```
abraflexi-mcp-server/
├── abraflexi_mcp_server/
│   ├── __init__.py
│   └── server.py                  # Main server implementation
├── appimage/
│   ├── AppRun                     # AppImage entry point
│   ├── abraflexi-mcp-server.desktop
│   ├── abraflexi-mcp-server.svg
│   └── build-appimage.sh          # AppImage build script
├── debian/                        # Debian packaging
│   ├── abraflexi-mcp-server.svg   # AppStream stock icon
│   ├── abraflexi-mcp-server.install
│   └── cz.vitexsoftware.abraflexi-mcp-server.metainfo.xml
├── scripts/
│   ├── start_server.py            # Startup script with validation
│   └── test_server.py             # Test script
├── Containerfile                  # OCI container build
├── server.json                    # MCP Registry manifest
├── pyproject.toml                 # Python project configuration
├── setup.py                       # Legacy setuptools configuration
├── requirements.txt               # Dependencies
├── .env.example                   # Environment configuration template
├── .env                           # Your configuration (not in git)
├── .gitignore                     # Git ignore patterns
└── README.md                      # This file
```

### Running Tests

```bash
# Tool registration + basic connectivity
uv run python scripts/test_server.py

# Live capability scenario (all read tools + READ_ONLY write guards)
# Official public demo (login winstrom / winstrom):
python tests/live_capability_scenario.py \
  --url https://demo.flexibee.eu:5434 \
  --company demo \
  --login winstrom --password winstrom \
  --json-out /tmp/abra-demo-live.json

# Private/dev company example:
python tests/live_capability_scenario.py \
  --url https://flexibee-dev.spoje.net:5434 \
  --company testa_invest_s_r_o_ \
  --login "$ABRAFLEXI_LOGIN" --password "$ABRAFLEXI_PASSWORD" \
  --json-out /tmp/abra-live.json
```

Exit code is non-zero when any non-skipped check fails.

## Error Handling

The server includes comprehensive error handling:

- ✅ Authentication errors are clearly reported
- 🔒 Read-only mode violations are blocked with descriptive messages
- ✔️ Invalid parameters are validated
- 🌐 Network and API errors are properly formatted
- 📝 Detailed logging for troubleshooting

## Security Considerations

- 🔑 Store credentials securely in `.env` file (never commit to git)
- 🔒 Enable read-only mode for monitoring-only use cases
- 🛡️ Use HTTPS for AbraFlexi server connections
- 🔄 Regularly rotate passwords
- 📁 Ensure `.env` file has proper permissions (600)

## Troubleshooting

### Common Issues

**Connection Failed:**
- Verify `ABRAFLEXI_URL` is correct and accessible
- Check authentication credentials
- Ensure AbraFlexi API is enabled
- Check firewall/network settings

**Permission Denied:**
- Verify user has sufficient AbraFlexi permissions
- Check if read-only mode is enabled when trying to modify data

**Tool Not Found:**
- Ensure all dependencies are installed: `uv sync`
- Verify Python version compatibility (3.10+)

### Debug Mode

Set environment variable for detailed logging:
```bash
export DEBUG=1
uv run python scripts/start_server.py
```

## Dependencies

- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
- [python-abraflexi](https://github.com/VitexSoftware/python-abraflexi) - AbraFlexi Python library
- [python-dotenv](https://github.com/theskumar/python-dotenv) - Environment variable management

## License

This project is licensed under the MIT License.

## Acknowledgments

- [AbraFlexi](https://www.abraflexi.eu/) for the accounting platform
- [Model Context Protocol](https://modelcontextprotocol.io/) for the integration standard
- [FastMCP](https://github.com/jlowin/fastmcp) for the server framework

## Support

- 📖 [Documentation](README.md)
- 🐛 [Issue Tracker](https://github.com/VitexSoftware/abraflexi-mcp-server/issues)
- 💬 [AbraFlexi API Documentation](https://podpora.flexibee.eu/cs/?q=API)

## Author

**Vítězslav Dvořák**
- Email: info@vitexsoftware.cz
- GitHub: [@VitexSoftware](https://github.com/VitexSoftware)

---

**Made with ❤️ for the AbraFlexi and MCP communities**

<!-- mcp-name: io.github.Vitexus/abraflexi -->
