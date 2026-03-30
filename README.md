# Copilot Tier Manager

Automate GitHub Copilot license tier assignments based on each user's monthly premium request unit (PRU) consumption.

## Why This Exists

GitHub Copilot Business includes **300 PRUs per user per month** and Enterprise includes **1,000 PRUs per user per month**. Unused PRUs **do not roll over** — they are use-it-or-lose-it each billing cycle. Organizations paying for Enterprise seats for users who consume far fewer than 300 PRUs are overspending, while Business users who regularly exceed their allowance generate costly overages.

This tool automates moving users between Copilot Business and Enterprise tiers based on actual PRU consumption so you only pay for what people use.

> **Stopgap solution.** GitHub's pooled billing model (targeted H2 2026) will make per-user PRU budgets obsolete. Until then, this automation bridges the gap.

## How It Works

The sync pipeline runs monthly (or on demand) and performs five steps:

1. **Fetch seat holders** — Reads all Copilot seat assignments and per-user PRU usage from the GitHub Enterprise API.
2. **Classify users** — The tier engine evaluates each user's PRU total against configurable thresholds defined in `config/tiers.yaml` and assigns them to a tier.
3. **Update Entra ID groups** — Moves users between four Microsoft Entra ID security groups via the Microsoft Graph API (adds to the new group first to prevent a zero-group state, then removes from the old group).
4. **SCIM sync** — Entra ID SCIM provisioning propagates group membership changes to GitHub Enterprise Teams automatically.
5. **Seat assignment** — Each Enterprise Team is pre-configured with a Copilot plan (Business or Enterprise), so users inherit the correct license.

```
GitHub Enterprise API ──► Tier Engine ──► Entra ID Groups ──(SCIM)──► Enterprise Teams ──► Copilot Seats
(PRU usage per user)      (classify)     (4 security groups)           (4 teams)            (Business/Enterprise)
```

## Tiers

| Tier | PRU Range | Copilot Plan | Overages | Description |
|------|-----------|-------------|----------|-------------|
| **basic-adopter** | 0 – 299 | Business | No | New or low-usage users within the included Copilot Business allowance |
| **growing-user** | 300 – 699 | Business | Yes | Active users exceeding the Business allowance, managed via an overage budget |
| **power-user** | 700 – 999 | Enterprise | No | High-usage users where Enterprise is more cost-effective than Business + overages |
| **advanced-user** | 1,000+ | Enterprise | Yes | Heavy users on Enterprise with overages enabled for full AI-assisted development |

Thresholds are fully configurable in `config/tiers.yaml`.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **GitHub Enterprise Cloud (EMU)** | Enterprise Managed Users org with Copilot enabled |
| **SCIM provisioning** | Configured between Microsoft Entra ID and the GitHub EMU Enterprise Application |
| **4 Entra ID security groups** | One per tier, assigned to the GitHub EMU Enterprise App in Entra ID |
| **4 GitHub Enterprise Teams** | Each linked to its Entra ID group via the SCIM `group_id` |
| **Copilot seat policies** | Each Enterprise Team assigned the appropriate Copilot plan (Business or Enterprise) |
| **GitHub PAT** | Scopes: `read:enterprise`, `admin:enterprise`, `manage_billing:copilot` |
| **Azure App Registration** | API permissions (Application): `GroupMember.ReadWrite.All`, `User.Read.All`, `Group.ReadWrite.All` |

## Setup

### 1. Clone and install

```bash
git clone https://github.com/your-org/copilot-tier-manager.git
cd copilot-tier-manager
pip install -r requirements.txt
```

### 2. Configure tiers

Copy the sample config and update it with your environment's values:

```bash
cp config/tiers.yaml config/tiers.local.yaml   # optional — keep defaults as reference
```

Edit `config/tiers.yaml` and set:

- `entra_group_id` for each tier (the Object ID of the Entra ID security group)
- `enterprise` — your GitHub Enterprise slug
- `emu_suffix` — the suffix appended to EMU usernames (e.g., `_contoso`)
- `emu_domain` — your Entra ID tenant domain for UPN resolution (e.g., `contoso.onmicrosoft.com`)
- `emu_username_separator` — character GitHub uses in EMU usernames (default: `-`)

### 3. Set environment variables

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub PAT with enterprise billing scopes |
| `AZURE_TENANT_ID` | Microsoft Entra ID tenant ID |
| `AZURE_CLIENT_ID` | App Registration client ID |
| `AZURE_CLIENT_SECRET` | App Registration client secret |
| `TEAMS_WEBHOOK_URL` | *(optional)* Microsoft Teams incoming webhook URL for notifications |

For local development you can authenticate interactively instead:

- **GitHub:** `gh auth login` (the tool falls back to `gh auth token`)
- **Azure:** `az login` (the tool falls back to `az account get-access-token`)

## Usage

```bash
# Dry run — preview tier changes without applying them
python -m src.sync --enterprise YOUR_ENTERPRISE --dry-run

# Execute — apply tier changes
python -m src.sync --enterprise YOUR_ENTERPRISE --execute

# Scope to a single org within the enterprise
python -m src.sync --enterprise YOUR_ENTERPRISE --org YOUR_ORG --execute

# Use a custom config file
python -m src.sync --enterprise YOUR_ENTERPRISE --config path/to/tiers.yaml --dry-run
```

All runs print a markdown summary to stdout. If `TEAMS_WEBHOOK_URL` is set, the summary is also posted to the configured Teams channel.

## GitHub Actions

A workflow is included at `.github/workflows/sync-tiers.yml`.

**Schedule:** Runs automatically on the **2nd of each month** at 06:00 UTC (the day after PRU counters reset). Scheduled runs default to **dry-run** mode — set the repository variable `COPILOT_TIER_DRY_RUN` to `false` to enable automatic execution.

**Manual dispatch:** Trigger from the Actions tab with a dry-run toggle and enterprise slug input.

### Required secrets

| Secret | Description |
|--------|-------------|
| `GH_ENTERPRISE_TOKEN` | GitHub PAT with enterprise billing scopes |
| `AZURE_TENANT_ID` | Microsoft Entra ID tenant ID |
| `AZURE_CLIENT_ID` | Azure App Registration client ID |
| `AZURE_CLIENT_SECRET` | Azure App Registration client secret |
| `TEAMS_WEBHOOK_URL` | *(optional)* Teams incoming webhook URL |

## Configuration

`config/tiers.yaml` reference:

```yaml
tiers:
  basic-adopter:
    min_pru: 0          # Lower bound (inclusive) of PRU usage for this tier
    max_pru: 299        # Upper bound (inclusive); null = unlimited
    entra_group_id: ""  # Object ID of the Entra ID security group
    copilot_plan: "business"   # "business" or "enterprise"
    overage_enabled: false     # Whether PRU overages are allowed
    description: "..."         # Human-readable description

# Global settings
enterprise: "your-enterprise"            # GitHub Enterprise slug
azure_tenant_id: "your-tenant-id"        # Entra ID tenant (informational)
emu_suffix: "_your-enterprise"           # Suffix on EMU usernames
emu_domain: "tenant.onmicrosoft.com"     # Entra ID domain for UPN lookup
emu_username_separator: "-"              # Separator in GitHub EMU usernames
```

Users are classified by finding the highest tier whose `min_pru` threshold they meet or exceed.

## Testing

```bash
# Unit tests — no authentication required
pytest tests/test_tier_engine.py -v

# Live integration tests — requires gh + az CLI auth
pytest tests/test_live.py -m live -v
```

## License

MIT
