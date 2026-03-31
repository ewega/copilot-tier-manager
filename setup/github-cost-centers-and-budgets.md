# Setting Up GitHub Cost Centers & Budgets

Configure cost centers and budgets to track and control Copilot spending across your four tiers. Each tier gets its own cost center linked to an enterprise team, with optional budgets for monitoring or capping spend.

## Prerequisites

| Requirement | Details |
|---|---|
| **GitHub Enterprise Cloud** | With Copilot Business and/or Enterprise enabled |
| **GitHub PAT** | Scopes: `admin:enterprise` (cost centers), `manage_billing:enterprise` (budgets) |
| **`gh` CLI** | Installed and authenticated (`gh auth login`) |
| **Enterprise teams** | One team per tier, linked to Entra ID groups via SCIM (see [Azure setup](azure-entra-id-setup.md)) |

## Quick Setup

### Option A: Automated Script

```bash
bash setup/scripts/setup-cost-centers.sh <your-enterprise-slug>
```

### Option B: AI-Assisted Setup (Copilot CLI / Agent)

Feed the prompt file to an AI agent to walk through the setup interactively:

```bash
cat setup/prompts/cost-centers-setup-prompt.md
```

Or start a [Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/cli-getting-started) session and paste the prompt.

> 📖 For a manual step-by-step walkthrough, follow the instructions in [`setup/prompts/cost-centers-setup-prompt.md`](prompts/cost-centers-setup-prompt.md).
