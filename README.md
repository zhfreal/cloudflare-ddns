# cloudflare-ddns

`cloudflare-ddns` is a lightweight, high-performance DDNS (Dynamic DNS) utility for Cloudflare, written in Go. It offers full support for Cloudflare's v7 DNS APIs, concurrent public IP resolution, and local record state caching for fast reconciliations.

It maintains 100% backward-compatibility for all legacy CLI flags while supporting modern nested subcommands.

---

## Features

- **Nested Subcommand Engine**:
  - `zones list`: List all zones registered in Cloudflare.
  - `records list/add/update/delete`: Subcommands to list, create, reconcile (DDNS), or delete DNS records.
- **100% Backward Compatibility**: Dynamically intercepts and rewrites legacy flags (e.g. `--list-record`, `--update-record`) to subcommands at runtime.
- **Concurrent IP Finder**: Resolves public IPv4/IPv6 addresses concurrently across multiple public API providers (`api64.ipify.org`, `ip.seeip.org`, `api.ip.sb/ip`) with 10-second timeout fallbacks.
- **Smart Delimiter Auto-Detection**: Auto-detects `,`, `;`, or `|` delimiters when processing raw string inputs.
- **Robust Reconciliation**: Supports a 4-phase DDNS reconciliation algorithm (update-in-place, re-purposing of surplus/extra records, clean-up deletes, and new creations).

---

## Installation

### From Source

Ensure you have Go installed (1.21 or later):
```bash
git clone -b feat/cloudflare-ddns-go https://github.com/zhfreal/cloudflare-ddns.git
cd cloudflare-ddns
make build
```
This compiles the executable as `./cloudflare-ddns`.

### Using Docker

```bash
docker build -t cloudflare-ddns .
```

---

## Configuration

`cloudflare-ddns` loads options in the following order of precedence:
1. **Command Line Flags** (e.g., `--api-token`)
2. **Environment Variables**:
   - `CLOUDFLARE_API_TOKEN` or `CF_API_TOKEN`
   - `CLOUDFLARE_EMAIL` or `CF_EMAIL`
   - `CLOUDFLARE_API_KEY` or `CF_API_KEY`
   - `HTTP_PROXY` and `HTTPS_PROXY`
3. **YAML Configuration Files** loaded from:
   - `~/.cloudflare-ddns.yaml`
   - `/etc/cloudflare-ddns.yaml`

Example YAML structure:
```yaml
api_token: "your-cloudflare-api-token"
email: "user@example.com"
api_key: "your-cloudflare-global-api-key"
ttl: 60
proxied: false
```

---

## Command Structure & Routing

`cloudflare-ddns` supports nested Go-style subcommands:

- **`zones`**:
  - **`list`** (aliases: `list-zone`, `list-zones`): List all registered zones.
- **`records`**:
  - **`list`** (aliases: `list-record`, `list-records`): List DNS records for a zone (with optional content filters).
  - **`add`** (aliases: `add-record`, `add-records`): Add a new DNS record.
  - **`update`** (aliases: `update-record`, `update-records`): Reconcile and update DNS records (DDNS engine).
  - **`delete`** (aliases: `delete-record`, `delete-records`): Delete DNS records.

### Flat Subcommands
You can call the aliases directly at the root level:
```bash
cloudflare-ddns list-zones
cloudflare-ddns update-records --zone example.com --alias sub --ipv4 fetch
```

### Legacy Flag Routing
All double-dash flags from the Python version are dynamically intercepted and routed. For example:
- `cloudflare-ddns --list-zone` is routed to `zones list`
- `cloudflare-ddns --update-record ...` is routed to `records update ...`

---

## Usage Examples

### 1. Listing Zones
```bash
# Subcommand
cloudflare-ddns zones list

# Legacy flag
cloudflare-ddns --list-zone
```

### 2. Listing DNS Records
```bash
# Subcommand
cloudflare-ddns records list --zone example.com

# Filter by record ID(s)
cloudflare-ddns records list --zone example.com --id record-id-1 --id record-id-2

# Legacy flag
cloudflare-ddns --list-record --zone example.com
```

### 3. Running DDNS (Reconciliation / Update)
```bash
# Update subdomain using resolved public IPv4 address
cloudflare-ddns records update --zone example.com --alias sub --ipv4 fetch

# Legacy flag syntax
cloudflare-ddns --update-record --zone example.com --alias sub --ipv4 fetch
```

### 4. Creating and Deleting Records
```bash
# Add a CNAME record
cloudflare-ddns records add --zone example.com --alias blog --cname ghs.google.com

# Delete an existing A record
cloudflare-ddns records delete --zone example.com --alias sub --ipv4 1.2.3.4

# Delete specific record(s) by ID
cloudflare-ddns records delete --zone example.com --id record-id-1 --id record-id-2
```

---

## Development

Use the included `Makefile` for developer tasks:

```bash
# Build the binary
make build

# Build for all OS/Arch combinations
make build-all

# Run the test suite
make test

# Clean build artifacts
make clean
```
