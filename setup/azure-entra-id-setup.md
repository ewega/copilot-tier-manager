# Setting Up Azure / Entra ID

## Quick Setup

Choose your preferred setup method:

### Option A: Automated Script

Run the provided script to set up everything automatically:

**Prerequisites:** `az` CLI authenticated with admin permissions, `gh` CLI authenticated with enterprise scopes, `jq` installed.

```bash
bash setup/setup-azure.sh \
    --enterprise <your-enterprise-slug> \
    --emu-app-id <github-emu-oidc-app-id> \
    --domain <your-company.onmicrosoft.com>
```

### Option B: AI-Assisted Setup (Copilot CLI / Agent)

Feed the step-by-step instructions to an AI agent (e.g. GitHub Copilot CLI) to walk through the setup interactively:

**Prerequisites:** Agent must have access to `az` CLI (authenticated) and `gh` CLI (authenticated with enterprise scopes).

```bash
# Copy the prompt file and paste it into your AI agent
cat setup/prompts/azure-setup-prompt.md
```

Or with Copilot CLI:
```bash
gh copilot suggest -t shell "$(cat setup/prompts/azure-setup-prompt.md)"
```

> 📖 For a detailed manual walkthrough, see the [step-by-step guide](#step-by-step-guide) below.

---

## Overview

The **Copilot Tier Manager** GitHub Action authenticates to [Microsoft Graph API](https://learn.microsoft.com/en-us/graph/overview) to manage Entra ID security group memberships. Users are classified into tiers based on their Premium Request Unit (PRU) consumption, and the action moves them between four Entra ID security groups accordingly. These groups are synced to GitHub Enterprise via SCIM provisioning, where they map to Enterprise Teams that control Copilot license assignments.

This guide walks you through the complete Azure / Entra ID setup required before the action can run.

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐     ┌───────────────┐
│ GitHub Action │────▶│ Microsoft Graph │────▶│ Entra ID Groups  │────▶│ SCIM ──▶ GitHub│
│ (this action) │     │ API             │     │ (4 tier groups)  │     │ Enterprise    │
└──────────────┘     └─────────────────┘     └──────────────────┘     └───────────────┘
```

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Azure tenant** | An Azure tenant with Microsoft Entra ID (formerly Azure AD) |
| **Azure CLI** | `az` CLI [installed](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) and authenticated with **Global Administrator** or **Application Administrator** permissions |
| **GitHub CLI** | `gh` CLI [installed](https://cli.github.com/) and authenticated with enterprise admin scopes |
| **GitHub EMU** | GitHub Enterprise Managed Users (EMU) with SCIM provisioning already configured |
| **GitHub EMU App ID** | The Application (client) ID of the GitHub EMU OIDC Enterprise Application in Entra ID (e.g. `12f6db80-...`) |
| **jq** | [jq](https://jqlang.github.io/jq/) installed for JSON processing in scripts |

---

## Step-by-Step Guide

### 1. Create App Registration

Create an Entra ID app registration that the GitHub Action will use to authenticate to Microsoft Graph.

```bash
# Create the app registration
az ad app create --display-name copilot-tier-manager

# Capture the Application (client) ID
APP_ID=$(az ad app list --display-name copilot-tier-manager --query "[0].appId" -o tsv)
echo "App ID: $APP_ID"

# Create a service principal for the app
az ad sp create --id "$APP_ID"

# Capture the service principal object ID
SP_OBJECT_ID=$(az ad sp list --filter "appId eq '$APP_ID'" --query "[0].id" -o tsv)
echo "Service Principal Object ID: $SP_OBJECT_ID"

# Generate a client secret (valid for 1 year)
az ad app credential reset --id "$APP_ID" --years 1
```

> **Important:** Save the `password` (client secret) from the output — it is shown only once. You will add it as a GitHub Actions secret later.

---

### 2. Grant Graph API Permissions

The app needs three Microsoft Graph **application** permissions:

| Permission | Purpose |
|------------|---------|
| `GroupMember.ReadWrite.All` | Add/remove users from tier security groups |
| `User.Read.All` | Look up users by UPN to resolve Entra object IDs |
| `Group.ReadWrite.All` | Read group information and membership |

```bash
# Microsoft Graph API well-known App ID
GRAPH_API="00000003-0000-0000-c000-000000000000"

# Permission IDs (these are stable, Microsoft-published GUIDs)
GROUP_MEMBER_RW="dbaae8cf-10b5-4b86-a4a1-f871c94c6571"   # GroupMember.ReadWrite.All
USER_READ_ALL="df021288-bdef-4463-88db-98f22de89214"       # User.Read.All
GROUP_RW_ALL="62a82d76-70ea-41e2-9197-370581804d09"        # Group.ReadWrite.All

# Add each permission
az ad app permission add --id "$APP_ID" --api "$GRAPH_API" --api-permissions \
    "$GROUP_MEMBER_RW=Role" \
    "$USER_READ_ALL=Role" \
    "$GROUP_RW_ALL=Role"

# Grant admin consent (requires Global Administrator or Privileged Role Administrator)
az ad app permission admin-consent --id "$APP_ID"
```

**Verify permissions were granted:**

```bash
az ad app permission list --id "$APP_ID" -o table
```

---

### 3. Create Entra ID Security Groups

Create four security groups — one for each Copilot usage tier:

```bash
# Basic Adopter (0–299 PRUs, Copilot Business)
az ad group create \
    --display-name "copilot-tier-basic-adopter" \
    --mail-nickname "copilot-tier-basic-adopter"

# Growing User (300–699 PRUs, Copilot Business + overages)
az ad group create \
    --display-name "copilot-tier-growing-user" \
    --mail-nickname "copilot-tier-growing-user"

# Power User (700–999 PRUs, Copilot Enterprise)
az ad group create \
    --display-name "copilot-tier-power-user" \
    --mail-nickname "copilot-tier-power-user"

# Advanced User (1000+ PRUs, Copilot Enterprise + overages)
az ad group create \
    --display-name "copilot-tier-advanced-user" \
    --mail-nickname "copilot-tier-advanced-user"
```

**Capture the group IDs** — you will need these for `config/tiers.yaml`:

```bash
TIERS=("copilot-tier-basic-adopter" "copilot-tier-growing-user" "copilot-tier-power-user" "copilot-tier-advanced-user")

for TIER in "${TIERS[@]}"; do
    GROUP_ID=$(az ad group show --group "$TIER" --query id -o tsv)
    echo "$TIER: $GROUP_ID"
done
```

---

### 4. Assign Groups to GitHub EMU App (SCIM)

For SCIM provisioning to sync these groups to GitHub, each group must be assigned to the GitHub EMU Enterprise Application in Entra ID.

```bash
# Your GitHub EMU OIDC Enterprise Application ID
EMU_APP_ID="<your-github-emu-app-id>"   # e.g. 12f6db80-...

# Get the service principal object ID for the EMU app
EMU_SP_ID=$(az ad sp list --filter "appId eq '$EMU_APP_ID'" --query "[0].id" -o tsv)
echo "EMU Service Principal ID: $EMU_SP_ID"

# Get the "User" app role ID from the EMU app
# (This is the default role that grants access to the application)
USER_ROLE_ID=$(az rest --method GET \
    --url "https://graph.microsoft.com/v1.0/servicePrincipals/$EMU_SP_ID" \
    --query "appRoles[?value=='User'].id | [0]" -o tsv)
echo "User Role ID: $USER_ROLE_ID"

# If no "User" role exists, use the default role (all zeros)
if [ -z "$USER_ROLE_ID" ]; then
    USER_ROLE_ID="00000000-0000-0000-0000-000000000000"
fi

# Assign each tier group to the EMU app
for TIER in "${TIERS[@]}"; do
    GROUP_ID=$(az ad group show --group "$TIER" --query id -o tsv)

    az rest --method POST \
        --url "https://graph.microsoft.com/v1.0/groups/$GROUP_ID/appRoleAssignments" \
        --headers "Content-Type=application/json" \
        --body "{
            \"principalId\": \"$GROUP_ID\",
            \"resourceId\": \"$EMU_SP_ID\",
            \"appRoleId\": \"$USER_ROLE_ID\"
        }"

    echo "✓ Assigned $TIER to GitHub EMU app"
done
```

---

### 5. Trigger SCIM Provisioning

After assigning groups, trigger the SCIM sync to push the groups to GitHub:

```bash
# Find the SCIM provisioning sync job
JOB_ID=$(az rest --method GET \
    --url "https://graph.microsoft.com/v1.0/servicePrincipals/$EMU_SP_ID/synchronization/jobs" \
    --query "value[0].id" -o tsv)
echo "Sync Job ID: $JOB_ID"

# Start the provisioning sync
az rest --method POST \
    --url "https://graph.microsoft.com/v1.0/servicePrincipals/$EMU_SP_ID/synchronization/jobs/$JOB_ID/start"

echo "✓ SCIM provisioning triggered — groups will appear in GitHub shortly"
```

**Monitor sync status:**

```bash
az rest --method GET \
    --url "https://graph.microsoft.com/v1.0/servicePrincipals/$EMU_SP_ID/synchronization/jobs/$JOB_ID" \
    --query "{status: status.code, lastRun: status.lastSuccessfulExecutionWithExportsSummary.timeBegan, progress: status.progress}" \
    -o json
```

> **Note:** SCIM provisioning can take a few minutes for initial sync. Wait until the groups appear in GitHub before proceeding to step 6.

---

### 6. Create GitHub Enterprise Teams Linked to SCIM Groups

Once SCIM has synced the groups to GitHub, create Enterprise Teams that are linked to the SCIM group IDs. These teams control Copilot license assignment.

```bash
ENTERPRISE="your-enterprise-slug"

# List the SCIM groups to get their IDs
gh api "/scim/v2/enterprises/$ENTERPRISE/Groups" \
    --jq '.Resources[] | "\(.displayName): \(.id)"'
```

This outputs something like:

```
copilot-tier-basic-adopter: abc12345-...
copilot-tier-growing-user: def67890-...
copilot-tier-power-user: ghi11111-...
copilot-tier-advanced-user: jkl22222-...
```

**Create an Enterprise Team for each group:**

```bash
# Create enterprise teams linked to SCIM groups
gh api "/enterprises/$ENTERPRISE/teams" --method POST \
    -f name="copilot-tier-basic-adopter" \
    -f group_id="<SCIM_GROUP_ID_FOR_BASIC>" \
    -H "X-GitHub-Api-Version:2026-03-10"

gh api "/enterprises/$ENTERPRISE/teams" --method POST \
    -f name="copilot-tier-growing-user" \
    -f group_id="<SCIM_GROUP_ID_FOR_GROWING>" \
    -H "X-GitHub-Api-Version:2026-03-10"

gh api "/enterprises/$ENTERPRISE/teams" --method POST \
    -f name="copilot-tier-power-user" \
    -f group_id="<SCIM_GROUP_ID_FOR_POWER>" \
    -H "X-GitHub-Api-Version:2026-03-10"

gh api "/enterprises/$ENTERPRISE/teams" --method POST \
    -f name="copilot-tier-advanced-user" \
    -f group_id="<SCIM_GROUP_ID_FOR_ADVANCED>" \
    -H "X-GitHub-Api-Version:2026-03-10"
```

> Replace each `<SCIM_GROUP_ID_FOR_...>` with the actual SCIM group ID from the previous command.

---

### 7. Assign Copilot Seats to Enterprise Teams

Finally, assign Copilot licenses to all four enterprise teams so that team membership controls seat allocation:

```bash
gh api "/enterprises/$ENTERPRISE/copilot/billing/selected_enterprise_teams" \
    --method POST \
    --input - <<< '{
        "selected_enterprise_teams": [
            "copilot-tier-basic-adopter",
            "copilot-tier-growing-user",
            "copilot-tier-power-user",
            "copilot-tier-advanced-user"
        ]
    }'
```

---

## Automated Setup Script

An automated script is provided to perform all the steps above in one go:

- **Script:** [`setup/setup-azure.sh`](setup-azure.sh)
- **Usage:** `bash setup/setup-azure.sh --enterprise <slug> --emu-app-id <app-id> --domain <domain>`

The script will create the app registration, security groups, SCIM assignments, enterprise teams, and Copilot seat assignments. Run `bash setup/setup-azure.sh --help` for full usage details.

---

## Storing Credentials

After running the setup (manually or via the script), store the credentials as GitHub Actions secrets.

### Required Secrets

| Secret | Value | Where to Find |
|--------|-------|---------------|
| `AZURE_TENANT_ID` | Your Azure tenant ID | `az account show --query tenantId -o tsv` |
| `AZURE_CLIENT_ID` | App registration client ID | Output from step 1, or Azure Portal → App registrations |
| `AZURE_CLIENT_SECRET` | App registration client secret | Output from `az ad app credential reset` (shown once) |
| `GH_ENTERPRISE_TOKEN` | GitHub PAT with enterprise scopes | GitHub → Settings → Developer settings → PATs |

### Setting Secrets via CLI

```bash
# Using GitHub CLI
gh secret set AZURE_TENANT_ID     --body "your-tenant-id"
gh secret set AZURE_CLIENT_ID     --body "your-client-id"
gh secret set AZURE_CLIENT_SECRET --body "your-client-secret"
gh secret set GH_ENTERPRISE_TOKEN --body "ghp_your-github-pat"
```

### Setting Secrets via GitHub UI

1. Navigate to your repository on GitHub.
2. Go to **Settings → Secrets and variables → Actions**.
3. Click **New repository secret** for each value above.

### Updating `config/tiers.yaml`

Update the Entra ID group IDs in your config file:

```yaml
tiers:
  basic-adopter:
    entra_group_id: "<group-id-from-step-3>"
    # ...
  growing-user:
    entra_group_id: "<group-id-from-step-3>"
    # ...
  power-user:
    entra_group_id: "<group-id-from-step-3>"
    # ...
  advanced-user:
    entra_group_id: "<group-id-from-step-3>"
    # ...

azure_tenant_id: "<your-tenant-id>"
enterprise: "<your-enterprise-slug>"
emu_suffix: "_<your-enterprise>"
emu_domain: "<your-domain>.onmicrosoft.com"
```

---

## Verifying Your Setup

Run these commands to verify each component is correctly configured.

### App Registration

```bash
# Verify the app exists and has correct permissions
az ad app show --id "$APP_ID" --query "{name:displayName, appId:appId}" -o table
az ad app permission list --id "$APP_ID" -o table

# Test authentication with the client credentials
curl -s -X POST "https://login.microsoftonline.com/$TENANT_ID/oauth2/v2.0/token" \
    -d "client_id=$APP_ID" \
    -d "client_secret=$CLIENT_SECRET" \
    -d "scope=https://graph.microsoft.com/.default" \
    -d "grant_type=client_credentials" | jq '.access_token | length'
# Should output a number (token length), not an error
```

### Security Groups

```bash
# Verify all four groups exist
for TIER in copilot-tier-basic-adopter copilot-tier-growing-user copilot-tier-power-user copilot-tier-advanced-user; do
    az ad group show --group "$TIER" --query "{name:displayName, id:id}" -o table
done
```

### SCIM Group Sync

```bash
# Verify groups are visible in GitHub via SCIM
gh api "/scim/v2/enterprises/$ENTERPRISE/Groups" \
    --jq '.Resources[] | select(.displayName | startswith("copilot-tier")) | "\(.displayName): \(.id)"'
```

### Enterprise Teams

```bash
# Verify enterprise teams exist and are linked to SCIM groups
gh api "/enterprises/$ENTERPRISE/teams" --jq '.[] | select(.name | startswith("copilot-tier")) | "\(.name) (group_id: \(.group_id // "none"))"'
```

### Copilot Seat Assignment

```bash
# Verify teams have Copilot seats assigned
gh api "/enterprises/$ENTERPRISE/copilot/billing/selected_enterprise_teams" \
    --jq '.enterprise_teams[].name'
```

### End-to-End Test (Dry Run)

```bash
# Run the action locally in dry-run mode
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret"
export GITHUB_TOKEN=$(gh auth token)

python -m src.sync --enterprise "$ENTERPRISE" --config config/tiers.yaml --dry-run
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `AADSTS7000215: Invalid client secret` | Client secret expired or incorrect | Regenerate: `az ad app credential reset --id $APP_ID --years 1` |
| `Authorization_RequestDenied` | Missing admin consent | Re-run: `az ad app permission admin-consent --id $APP_ID` |
| SCIM groups not appearing in GitHub | SCIM sync not triggered or groups not assigned to EMU app | Re-run steps 4 and 5 |
| Enterprise team creation fails | SCIM group not yet synced | Wait a few minutes, verify with SCIM groups check above |
| `Resource not found` on `/enterprises/...` | Wrong enterprise slug or missing PAT scopes | Verify `$ENTERPRISE` and PAT has `admin:enterprise` scope |
| Group membership changes not syncing | SCIM provisioning paused | Check sync status in Entra ID → Enterprise Applications → GitHub EMU → Provisioning |
