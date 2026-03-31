#!/bin/bash
# =============================================================================
# setup-cost-centers.sh — Create GitHub Cost Centers & Budgets for Copilot tiers
# =============================================================================
# Usage: ./setup-cost-centers.sh <enterprise-slug>
#
# Prerequisites:
#   - gh CLI installed and authenticated
#   - PAT with admin:enterprise and manage_billing:enterprise scopes
# =============================================================================

set -euo pipefail

ENTERPRISE="${1:?Usage: $0 <enterprise-slug>}"

TIERS=("basic-adopter" "growing-user" "power-user" "advanced-user")

# ---------------------------------------------------------------------------
# 1. Create cost centers
# ---------------------------------------------------------------------------
echo "=== Creating cost centers for enterprise: $ENTERPRISE ==="

declare -A COST_CENTER_IDS

for TIER in "${TIERS[@]}"; do
    NAME="copilot-tier-$TIER"
    echo "  Creating cost center: $NAME"
    RESPONSE=$(gh api "/enterprises/$ENTERPRISE/settings/billing/cost-centers" \
        --method POST \
        -f name="$NAME" \
        2>&1) || {
        echo "  ⚠ Failed to create $NAME (may already exist)"
        echo "  $RESPONSE"
        continue
    }
    ID=$(echo "$RESPONSE" | gh api --jq '.id' --input - 2>/dev/null || echo "unknown")
    COST_CENTER_IDS[$TIER]="$ID"
    echo "  ✓ Created: $NAME (id: $ID)"
done

# ---------------------------------------------------------------------------
# 2. List created cost centers (and capture IDs if creation returned them)
# ---------------------------------------------------------------------------
echo ""
echo "=== Current cost centers ==="
gh api "/enterprises/$ENTERPRISE/settings/billing/cost-centers" \
    --jq '.cost_centers[] | "  \(.name): \(.id)"' 2>&1 || echo "  (unable to list — check permissions)"

# ---------------------------------------------------------------------------
# 3. Create budgets
# ---------------------------------------------------------------------------
echo ""
echo "=== Creating budgets ==="
echo ""
echo "⚠  Budget creation requires the manage_billing:enterprise scope."
echo "   If your current token only has admin:enterprise, budget calls will fail."
echo ""

# To create budgets, you need the cost center IDs from the listing above.
# Update these values after running the cost center creation step.
echo "To create budgets, run the following commands with the cost center IDs"
echo "from the listing above:"
echo ""

cat <<'BUDGET_COMMANDS'
# Alert-only budget for Basic Adopter (no overages expected)
gh api "/enterprises/$ENTERPRISE/settings/billing/budgets" \
    --method POST \
    -f cost_center_id="<basic-adopter-cost-center-id>" \
    -f limit_type="notifications_only" \
    -F alert_threshold=80 \
    -f name="copilot-tier-basic-adopter-budget"

# Hard-cap budget for Growing User (controls Business overages)
gh api "/enterprises/$ENTERPRISE/settings/billing/budgets" \
    --method POST \
    -f cost_center_id="<growing-user-cost-center-id>" \
    -f limit_type="hard_cap" \
    -F amount=2000 \
    -F alert_threshold=80 \
    -f name="copilot-tier-growing-user-budget"

# Alert-only budget for Power User (Enterprise included PRUs)
gh api "/enterprises/$ENTERPRISE/settings/billing/budgets" \
    --method POST \
    -f cost_center_id="<power-user-cost-center-id>" \
    -f limit_type="notifications_only" \
    -F alert_threshold=80 \
    -f name="copilot-tier-power-user-budget"

# Hard-cap budget for Advanced User (controls Enterprise overages)
gh api "/enterprises/$ENTERPRISE/settings/billing/budgets" \
    --method POST \
    -f cost_center_id="<advanced-user-cost-center-id>" \
    -f limit_type="hard_cap" \
    -F amount=5000 \
    -F alert_threshold=80 \
    -f name="copilot-tier-advanced-user-budget"
BUDGET_COMMANDS

echo ""
echo "=== Done ==="
echo "Next steps:"
echo "  1. Copy the cost center IDs from the listing above"
echo "  2. Run the budget commands with the correct IDs"
echo "  3. Assign enterprise teams to cost centers (see guide)"
