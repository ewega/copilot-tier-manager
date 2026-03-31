#!/usr/bin/env bash
# ==============================================================================
# setup-azure.sh — Automated Azure / Entra ID setup for Copilot Tier Manager
#
# Creates the app registration, security groups, SCIM assignments, GitHub
# enterprise teams, and Copilot seat assignments required by the action.
#
# Usage:
#   bash setup-azure.sh \
#       --enterprise <github-enterprise-slug> \
#       --emu-app-id <github-emu-oidc-app-id> \
#       --domain <entra-domain>
#
# Example:
#   bash setup-azure.sh \
#       --enterprise mycompany \
#       --emu-app-id 12f6db80-abcd-1234-ef56-789012345678 \
#       --domain mycompany.onmicrosoft.com
# ==============================================================================
set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}ℹ ${NC}$*"; }
success() { echo -e "${GREEN}✓ ${NC}$*"; }
warn()    { echo -e "${YELLOW}⚠ ${NC}$*"; }
error()   { echo -e "${RED}✗ ${NC}$*" >&2; }

# ── Parse arguments ──────────────────────────────────────────────────────────
ENTERPRISE=""
EMU_APP_ID=""
DOMAIN=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --enterprise)  ENTERPRISE="$2";  shift 2 ;;
        --emu-app-id)  EMU_APP_ID="$2";  shift 2 ;;
        --domain)      DOMAIN="$2";      shift 2 ;;
        -h|--help)
            echo "Usage: $0 --enterprise <slug> --emu-app-id <app-id> --domain <domain>"
            exit 0 ;;
        *) error "Unknown argument: $1"; exit 1 ;;
    esac
done

if [[ -z "$ENTERPRISE" || -z "$EMU_APP_ID" || -z "$DOMAIN" ]]; then
    error "Missing required arguments."
    echo "Usage: $0 --enterprise <slug> --emu-app-id <app-id> --domain <domain>"
    exit 1
fi

TIERS=("copilot-tier-basic-adopter" "copilot-tier-growing-user" "copilot-tier-power-user" "copilot-tier-advanced-user")

# ── Pre-flight checks ────────────────────────────────────────────────────────
info "Checking prerequisites..."
command -v az  >/dev/null 2>&1 || { error "Azure CLI (az) is not installed."; exit 1; }
command -v gh  >/dev/null 2>&1 || { error "GitHub CLI (gh) is not installed."; exit 1; }
command -v jq  >/dev/null 2>&1 || { error "jq is not installed."; exit 1; }

az account show >/dev/null 2>&1 || { error "Not logged into Azure CLI. Run: az login"; exit 1; }
gh auth status  >/dev/null 2>&1 || { error "Not logged into GitHub CLI. Run: gh auth login"; exit 1; }
success "All prerequisites met."

# ── Confirm before proceeding ─────────────────────────────────────────────────
echo ""
echo "This script will:"
echo "  1. Create an Entra ID app registration: copilot-tier-manager"
echo "  2. Grant Microsoft Graph API permissions (admin consent)"
echo "  3. Create 4 security groups in Entra ID"
echo "  4. Assign groups to the GitHub EMU app for SCIM sync"
echo "  5. Trigger SCIM provisioning"
echo "  6. Create GitHub Enterprise Teams linked to SCIM groups"
echo "  7. Assign Copilot seats to the enterprise teams"
echo ""
echo "  Enterprise:   $ENTERPRISE"
echo "  EMU App ID:   $EMU_APP_ID"
echo "  Domain:       $DOMAIN"
echo ""
read -rp "Proceed? (y/N) " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

# ==============================================================================
# Step 1: Create App Registration
# ==============================================================================
echo ""
info "Step 1/7: Creating app registration..."

EXISTING_APP_ID=$(az ad app list --display-name "copilot-tier-manager" --query "[0].appId" -o tsv 2>/dev/null || true)

if [[ -n "$EXISTING_APP_ID" ]]; then
    warn "App registration 'copilot-tier-manager' already exists (App ID: $EXISTING_APP_ID)."
    read -rp "Use existing app? (y/N) " use_existing
    if [[ "$use_existing" == "y" || "$use_existing" == "Y" ]]; then
        APP_ID="$EXISTING_APP_ID"
    else
        error "Please delete the existing app first: az ad app delete --id $EXISTING_APP_ID"
        exit 1
    fi
else
    az ad app create --display-name "copilot-tier-manager" >/dev/null
    APP_ID=$(az ad app list --display-name "copilot-tier-manager" --query "[0].appId" -o tsv)
    success "App registration created."
fi

# Create service principal
SP_EXISTS=$(az ad sp list --filter "appId eq '$APP_ID'" --query "[0].id" -o tsv 2>/dev/null || true)
if [[ -z "$SP_EXISTS" ]]; then
    az ad sp create --id "$APP_ID" >/dev/null
    success "Service principal created."
else
    info "Service principal already exists."
fi
SP_OBJECT_ID=$(az ad sp list --filter "appId eq '$APP_ID'" --query "[0].id" -o tsv)

# Generate client secret
info "Generating client secret (valid for 1 year)..."
CRED_OUTPUT=$(az ad app credential reset --id "$APP_ID" --years 1 -o json)
CLIENT_SECRET=$(echo "$CRED_OUTPUT" | jq -r '.password')
TENANT_ID=$(echo "$CRED_OUTPUT" | jq -r '.tenant')

success "App registration ready."
echo "  App ID (Client ID):      $APP_ID"
echo "  SP Object ID:            $SP_OBJECT_ID"
echo "  Tenant ID:               $TENANT_ID"
echo "  Client Secret:           ****** (saved for output at the end)"

# ==============================================================================
# Step 2: Grant Graph API Permissions
# ==============================================================================
echo ""
info "Step 2/7: Granting Graph API permissions..."

GRAPH_API="00000003-0000-0000-c000-000000000000"
GROUP_MEMBER_RW="dbaae8cf-10b5-4b86-a4a1-f871c94c6571"
USER_READ_ALL="df021288-bdef-4463-88db-98f22de89214"
GROUP_RW_ALL="62a82d76-70ea-41e2-9197-370581804d09"

az ad app permission add --id "$APP_ID" --api "$GRAPH_API" --api-permissions \
    "$GROUP_MEMBER_RW=Role" \
    "$USER_READ_ALL=Role" \
    "$GROUP_RW_ALL=Role" 2>/dev/null || true

info "Granting admin consent (may require Global Administrator)..."
az ad app permission admin-consent --id "$APP_ID"
success "Graph API permissions granted and consented."

# ==============================================================================
# Step 3: Create Security Groups
# ==============================================================================
echo ""
info "Step 3/7: Creating Entra ID security groups..."

declare -A GROUP_IDS
for TIER in "${TIERS[@]}"; do
    EXISTING_GID=$(az ad group show --group "$TIER" --query id -o tsv 2>/dev/null || true)
    if [[ -n "$EXISTING_GID" ]]; then
        warn "Group '$TIER' already exists: $EXISTING_GID"
        GROUP_IDS[$TIER]="$EXISTING_GID"
    else
        az ad group create --display-name "$TIER" --mail-nickname "$TIER" >/dev/null
        GID=$(az ad group show --group "$TIER" --query id -o tsv)
        GROUP_IDS[$TIER]="$GID"
        success "Created $TIER: $GID"
    fi
done

echo ""
info "Group IDs:"
for TIER in "${TIERS[@]}"; do
    echo "  $TIER: ${GROUP_IDS[$TIER]}"
done

# ==============================================================================
# Step 4: Assign Groups to GitHub EMU App
# ==============================================================================
echo ""
info "Step 4/7: Assigning groups to GitHub EMU Enterprise App..."

EMU_SP_ID=$(az ad sp list --filter "appId eq '$EMU_APP_ID'" --query "[0].id" -o tsv 2>/dev/null || true)

if [[ -z "$EMU_SP_ID" ]]; then
    error "Could not find service principal for EMU App ID: $EMU_APP_ID"
    error "Verify the app ID is correct and the Enterprise App exists in your tenant."
    exit 1
fi
info "EMU Service Principal ID: $EMU_SP_ID"

# Get the User app role ID
USER_ROLE_ID=$(az rest --method GET \
    --url "https://graph.microsoft.com/v1.0/servicePrincipals/$EMU_SP_ID" \
    --query "appRoles[?value=='User'].id | [0]" -o tsv 2>/dev/null || true)

if [[ -z "$USER_ROLE_ID" || "$USER_ROLE_ID" == "None" ]]; then
    USER_ROLE_ID="00000000-0000-0000-0000-000000000000"
    info "No 'User' app role found — using default role."
fi

for TIER in "${TIERS[@]}"; do
    GID="${GROUP_IDS[$TIER]}"
    az rest --method POST \
        --url "https://graph.microsoft.com/v1.0/groups/$GID/appRoleAssignments" \
        --headers "Content-Type=application/json" \
        --body "{
            \"principalId\": \"$GID\",
            \"resourceId\": \"$EMU_SP_ID\",
            \"appRoleId\": \"$USER_ROLE_ID\"
        }" >/dev/null 2>&1 || warn "Assignment for $TIER may already exist (this is OK)."
    success "Assigned $TIER to EMU app."
done

# ==============================================================================
# Step 5: Trigger SCIM Provisioning
# ==============================================================================
echo ""
info "Step 5/7: Triggering SCIM provisioning sync..."

JOB_ID=$(az rest --method GET \
    --url "https://graph.microsoft.com/v1.0/servicePrincipals/$EMU_SP_ID/synchronization/jobs" \
    --query "value[0].id" -o tsv 2>/dev/null || true)

if [[ -z "$JOB_ID" ]]; then
    warn "No SCIM sync job found. SCIM provisioning may not be configured."
    warn "Skipping sync trigger — configure SCIM provisioning manually in Entra ID."
else
    az rest --method POST \
        --url "https://graph.microsoft.com/v1.0/servicePrincipals/$EMU_SP_ID/synchronization/jobs/$JOB_ID/start" \
        2>/dev/null || warn "Sync may already be running."
    success "SCIM provisioning triggered (Job ID: $JOB_ID)."
fi

# Wait for SCIM to sync groups
info "Waiting 60 seconds for SCIM provisioning to sync groups to GitHub..."
sleep 60

# ==============================================================================
# Step 6: Create GitHub Enterprise Teams
# ==============================================================================
echo ""
info "Step 6/7: Creating GitHub Enterprise Teams linked to SCIM groups..."

# Fetch SCIM group IDs
SCIM_GROUPS=$(gh api "/scim/v2/enterprises/$ENTERPRISE/Groups" --jq '.Resources[] | "\(.displayName)|\(.id)"' 2>/dev/null || true)

if [[ -z "$SCIM_GROUPS" ]]; then
    warn "No SCIM groups found in GitHub yet. SCIM sync may still be in progress."
    warn "Re-run this step manually once groups appear:"
    echo '  gh api "/scim/v2/enterprises/'"$ENTERPRISE"'/Groups" --jq '"'"'.Resources[] | "\(.displayName): \(.id)"'"'"
    echo ""
    warn "Then create teams with:"
    echo '  gh api "/enterprises/'"$ENTERPRISE"'/teams" --method POST -f name="<group>" -f group_id="<scim-id>" -H "X-GitHub-Api-Version:2026-03-10"'
else
    declare -A SCIM_IDS
    while IFS='|' read -r name id; do
        SCIM_IDS[$name]="$id"
    done <<< "$SCIM_GROUPS"

    for TIER in "${TIERS[@]}"; do
        SCIM_ID="${SCIM_IDS[$TIER]:-}"
        if [[ -z "$SCIM_ID" ]]; then
            warn "SCIM group not found for $TIER — skipping."
            continue
        fi
        gh api "/enterprises/$ENTERPRISE/teams" --method POST \
            -f name="$TIER" \
            -f group_id="$SCIM_ID" \
            -H "X-GitHub-Api-Version:2026-03-10" >/dev/null 2>&1 \
            && success "Created enterprise team: $TIER" \
            || warn "Team $TIER may already exist."
    done
fi

# ==============================================================================
# Step 7: Assign Copilot Seats
# ==============================================================================
echo ""
info "Step 7/7: Assigning Copilot seats to enterprise teams..."

gh api "/enterprises/$ENTERPRISE/copilot/billing/selected_enterprise_teams" \
    --method POST \
    --input - <<< "{
        \"selected_enterprise_teams\": [
            \"copilot-tier-basic-adopter\",
            \"copilot-tier-growing-user\",
            \"copilot-tier-power-user\",
            \"copilot-tier-advanced-user\"
        ]
    }" >/dev/null 2>&1 \
    && success "Copilot seats assigned to all tier teams." \
    || warn "Copilot seat assignment failed — you may need to do this manually."

# ==============================================================================
# Summary
# ==============================================================================
echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "  SETUP COMPLETE — Save these values"
echo "════════════════════════════════════════════════════════════════════════"
echo ""
echo "  AZURE_TENANT_ID:      $TENANT_ID"
echo "  AZURE_CLIENT_ID:      $APP_ID"
echo "  AZURE_CLIENT_SECRET:  $CLIENT_SECRET"
echo "  COPILOT_ENTERPRISE:   $ENTERPRISE"
echo ""
echo "  Entra ID Group IDs (for config/tiers.yaml):"
for TIER in "${TIERS[@]}"; do
    echo "    $TIER: ${GROUP_IDS[$TIER]}"
done
echo ""
echo "  Add these as GitHub Actions secrets:"
echo "    gh secret set AZURE_TENANT_ID     --body \"$TENANT_ID\""
echo "    gh secret set AZURE_CLIENT_ID     --body \"$APP_ID\""
echo "    gh secret set AZURE_CLIENT_SECRET --body \"<paste secret>\""
echo ""
echo "  ⚠  The client secret above is shown only once. Store it securely!"
echo "════════════════════════════════════════════════════════════════════════"
