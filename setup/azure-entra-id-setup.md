# Setting Up Azure / Entra ID

This guide sets up the Azure / Entra ID infrastructure for the Copilot Tier Manager: an app registration, four security groups, SCIM provisioning, and GitHub Enterprise Teams. The action uses Microsoft Graph API to move users between Entra ID groups based on PRU consumption.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Azure tenant** | An Azure tenant with Microsoft Entra ID (formerly Azure AD) |
| **Azure CLI** | `az` CLI [installed](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) and authenticated with **Global Administrator** or **Application Administrator** permissions |
| **GitHub CLI** | `gh` CLI [installed](https://cli.github.com/) and authenticated with enterprise admin scopes |
| **GitHub EMU** | GitHub Enterprise Managed Users (EMU) with SCIM provisioning already configured |
| **GitHub EMU App ID** | The Application (client) ID of the GitHub EMU OIDC Enterprise Application in Entra ID (e.g. `12f6db80-...`) |
| **jq** | [jq](https://jqlang.github.io/jq/) installed for JSON processing in scripts |

## Quick Setup

### Option A: Automated Script

```bash
bash setup/scripts/setup-azure.sh \
    --enterprise <your-enterprise-slug> \
    --emu-app-id <github-emu-oidc-app-id> \
    --domain <your-company.onmicrosoft.com>
```

Run `bash setup/scripts/setup-azure.sh --help` for full usage details.

### Option B: AI-Assisted Setup (Copilot CLI / Agent)

Feed the prompt file to an AI agent to walk through the setup interactively:

```bash
cat setup/prompts/azure-setup-prompt.md
```

Or start a [Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/cli-getting-started) session and paste the prompt.

> 📖 For a manual step-by-step walkthrough, follow the instructions in [`setup/prompts/azure-setup-prompt.md`](prompts/azure-setup-prompt.md).
