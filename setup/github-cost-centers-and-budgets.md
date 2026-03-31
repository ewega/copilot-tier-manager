# Setting Up GitHub Cost Centers & Budgets

## Quick Setup

Choose your preferred setup method:

### Option A: Automated Script

```bash
bash setup/setup-cost-centers.sh <your-enterprise-slug>
```

**Prerequisites:** `gh` CLI authenticated with `admin:enterprise` and `manage_billing:enterprise` scopes.

### Option B: AI-Assisted Setup (Copilot CLI / Agent)

**Prerequisites:** Agent must have access to `gh` CLI authenticated with enterprise scopes.

```bash
cat setup/prompts/cost-centers-setup-prompt.md
```

Or start a [Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/cli-getting-started) session and paste the prompt:
```bash
copilot
# Then paste the contents of setup/prompts/cost-centers-setup-prompt.md
```

> 📖 For a detailed manual walkthrough, see the [step-by-step guide](#step-by-step-guide) below.

---

> Configure cost centers and budgets to track and control Copilot spending across your 4 tiers.

---

## Overview

GitHub's **Cost Centers** let you group users (via enterprise teams) and attribute their Copilot spending to a logical unit. **Budgets** attach spending limits or alerts to those cost centers.

For the Copilot Tier Manager, you create one cost center per tier:

| Cost Center | Tier | Copilot Plan | PRU Range |
|---|---|---|---|
| `copilot-tier-basic-adopter` | 🟢 Basic Adopter | Business | 0–299 |
| `copilot-tier-growing-user` | 🟡 Growing User | Business + overages | 300–699 |
| `copilot-tier-power-user` | 🔴 Power User | Enterprise | 700–999 |
| `copilot-tier-advanced-user` | 🟣 Advanced User | Enterprise + overages | 1,000+ |

Each cost center gets a budget so you can monitor (or cap) spend per tier independently.

---

## Prerequisites

| Requirement | Details |
|---|---|
| **GitHub Enterprise Cloud** | With Copilot Business and/or Enterprise enabled |
| **GitHub PAT** | Scopes: `admin:enterprise` (cost centers), `manage_billing:enterprise` (budgets) |
| **`gh` CLI** | Installed and authenticated (`gh auth login`) |
| **Enterprise teams** | One team per tier, linked to Entra ID groups via SCIM (see main [README](../README.md)) |

### Verify your PAT scopes

```bash
# Check that your token has the required scopes
gh auth status
```

Your token must include both `admin:enterprise` and `manage_billing:enterprise`. If you're using a fine-grained PAT, ensure the equivalent enterprise permissions are granted.

---

## Step-by-Step Guide

### 1. Create Cost Centers

Cost centers are created via the enterprise billing API. Each cost center needs a unique name and can be linked to enterprise teams.

**API endpoint:**

```
POST /enterprises/{enterprise}/settings/billing/cost-centers
```

**Required scope:** `admin:enterprise`

#### Create a cost center for each tier

```bash
ENTERPRISE="your-enterprise-slug"

# Basic Adopter tier
gh api "/enterprises/$ENTERPRISE/settings/billing/cost-centers" \
    --method POST \
    -f name="copilot-tier-basic-adopter"

# Growing User tier
gh api "/enterprises/$ENTERPRISE/settings/billing/cost-centers" \
    --method POST \
    -f name="copilot-tier-growing-user"

# Power User tier
gh api "/enterprises/$ENTERPRISE/settings/billing/cost-centers" \
    --method POST \
    -f name="copilot-tier-power-user"

# Advanced User tier
gh api "/enterprises/$ENTERPRISE/settings/billing/cost-centers" \
    --method POST \
    -f name="copilot-tier-advanced-user"
```

#### Verify cost centers were created

```bash
gh api "/enterprises/$ENTERPRISE/settings/billing/cost-centers" \
    --jq '.cost_centers[] | "\(.name): \(.id)"'
```

> **Note:** Save the returned `id` values — you'll need them when creating budgets and assigning teams.

---

### 2. Create Budgets

Budgets control or monitor spending for a cost center. GitHub supports two budget behaviors:

| Type | Behavior | Use Case |
|---|---|---|
| **Alert-only** | Sends notifications at the threshold; no spending cap | Monitoring tiers — know when a tier is trending high |
| **Hard cap** | Stops additional usage once the budget is exhausted | Controlling overage tiers — prevent runaway spend |

**API endpoint:**

```
POST /enterprises/{enterprise}/settings/billing/budgets
```

**Required scope:** `manage_billing:enterprise`

#### Example: Alert-only budget (recommended for most tiers)

```bash
ENTERPRISE="your-enterprise-slug"
COST_CENTER_ID="<cost-center-id-from-step-1>"

gh api "/enterprises/$ENTERPRISE/settings/billing/budgets" \
    --method POST \
    -f cost_center_id="$COST_CENTER_ID" \
    -f limit_type="notifications_only" \
    -F alert_threshold=80 \
    -f name="copilot-tier-basic-adopter-budget"
```

This sends an alert when 80% of the expected budget is consumed, but does **not** block usage.

#### Example: Hard-cap budget (for overage tiers)

```bash
gh api "/enterprises/$ENTERPRISE/settings/billing/budgets" \
    --method POST \
    -f cost_center_id="$COST_CENTER_ID" \
    -f limit_type="hard_cap" \
    -F amount=5000 \
    -F alert_threshold=80 \
    -f name="copilot-tier-advanced-user-budget"
```

This caps spending at $5,000 and sends an alert at 80% ($4,000).

#### Recommended budget strategy per tier

| Cost Center | Budget Type | Rationale |
|---|---|---|
| `copilot-tier-basic-adopter` | Alert-only | Low-usage users; no overages expected |
| `copilot-tier-growing-user` | Hard cap | Controls Business overage spend |
| `copilot-tier-power-user` | Alert-only | Enterprise seats have included PRUs |
| `copilot-tier-advanced-user` | Hard cap | Controls Enterprise overage spend |

---

### 3. Assign Enterprise Teams to Cost Centers

After creating cost centers, link each enterprise team (which maps to an Entra ID group via SCIM) to its corresponding cost center.

```bash
ENTERPRISE="your-enterprise-slug"
COST_CENTER_ID="<cost-center-id>"
TEAM_SLUG="copilot-tier-basic-adopter"

gh api "/enterprises/$ENTERPRISE/settings/billing/cost-centers/$COST_CENTER_ID/resource" \
    --method POST \
    -f resource_type="team" \
    -f resource_id="$TEAM_SLUG"
```

Repeat for each tier, mapping the team slug to the correct cost center ID.

> **Tip:** Your enterprise teams should already exist if you've set up SCIM provisioning from Entra ID. See the main [README](../README.md) prerequisites.

---

## Automated Setup Script

An automated script is provided to create all cost centers and budgets:

- **Script:** [`setup/setup-cost-centers.sh`](setup-cost-centers.sh)
- **Usage:** `bash setup/setup-cost-centers.sh <enterprise-slug>`

The script creates 4 cost centers (one per tier) and provides commands for budget creation.

---

## Verifying Your Setup

### List all cost centers

```bash
gh api "/enterprises/$ENTERPRISE/settings/billing/cost-centers" \
    --jq '.cost_centers[] | {name, id, resources: [.resources[]?.resource_id]}'
```

### List all budgets

```bash
gh api "/enterprises/$ENTERPRISE/settings/billing/budgets" \
    --jq '.budgets[] | {name, limit_type, amount, alert_threshold, cost_center_id}'
```

### Verify team-to-cost-center assignments

```bash
# Check a specific cost center's assigned resources
COST_CENTER_ID="<your-cost-center-id>"

gh api "/enterprises/$ENTERPRISE/settings/billing/cost-centers/$COST_CENTER_ID" \
    --jq '.resources[] | "\(.resource_type): \(.resource_id)"'
```

### End-to-end check

```bash
echo "=== Copilot Tier Billing Setup ==="
echo ""
echo "Cost Centers:"
gh api "/enterprises/$ENTERPRISE/settings/billing/cost-centers" \
    --jq '.cost_centers[] | "  [\(.id)] \(.name) — resources: \([.resources[]?.resource_id] | join(", "))"'
echo ""
echo "Budgets:"
gh api "/enterprises/$ENTERPRISE/settings/billing/budgets" \
    --jq '.budgets[] | "  \(.name) — \(.limit_type) \(if .amount then "(cap: $\(.amount))" else "" end) alert@\(.alert_threshold)%"'
```

---

## Troubleshooting

### `Resource not accessible by personal access token`

Your PAT is missing the required scope.

| Operation | Required Scope |
|---|---|
| Create/list cost centers | `admin:enterprise` |
| Create/list budgets | `manage_billing:enterprise` |
| Assign teams to cost centers | `admin:enterprise` |

**Fix:** Regenerate your PAT with both scopes, or use a fine-grained token with equivalent enterprise permissions.

### `Not Found` on the enterprise endpoint

```
gh: Not Found (HTTP 404)
```

- Verify your enterprise slug: `gh api /enterprises/YOUR-SLUG`
- Ensure your account is an **enterprise owner** or has delegated billing admin rights
- Check that Enterprise Cloud billing APIs are available for your plan

### `Cost center name already exists`

Cost center names must be unique within an enterprise. If you get a conflict:

```bash
# List existing cost centers to find duplicates
gh api "/enterprises/$ENTERPRISE/settings/billing/cost-centers" \
    --jq '.cost_centers[] | "\(.name): \(.id)"'
```

Either reuse the existing cost center or delete and recreate it.

### SKU-related errors

Budget creation may reference Copilot-specific SKUs (e.g., `spark_premium_request`). If you encounter SKU errors:

- The available SKUs depend on your enterprise's Copilot plan and billing configuration
- Check available SKUs:
  ```bash
  gh api "/enterprises/$ENTERPRISE/settings/billing/usage" \
      --jq '.usageItems[] | select(.product | test("copilot"; "i")) | .sku'
  ```
- Contact GitHub Support if expected SKUs are not available

### Budget not enforcing hard cap

- Verify the budget's `limit_type` is `"hard_cap"` (not `"notifications_only"`)
- Hard caps may take a few minutes to propagate
- Some Copilot usage (e.g., in-flight requests) may exceed the cap slightly before enforcement kicks in

### Teams not appearing in cost center

- Ensure the team exists at the **enterprise** level (not just the org level)
- Verify SCIM provisioning is active and the Entra ID group is synced
- Check the team slug matches exactly (case-sensitive)

---

## Related Documentation

- [GitHub Billing REST API](https://docs.github.com/en/rest/billing)
- [Managing cost centers](https://docs.github.com/en/enterprise-cloud@latest/billing/using-the-new-billing-platform/managing-your-cost-centers)
- [Managing budgets](https://docs.github.com/en/enterprise-cloud@latest/billing/using-the-new-billing-platform/managing-your-budgets)
- [Copilot Tier Manager README](../README.md)
- [Tier configuration](../config/tiers.yaml)
