# GitHub Cost Centers & Budgets Setup for Copilot Tier Manager

You are setting up GitHub Cost Centers and Budgets for the Copilot Tier Manager. You have access to `gh` CLI authenticated with `admin:enterprise` and `manage_billing:enterprise` scopes.

## What You Need to Create

1. **4 Cost Centers** in the GitHub Enterprise:
   - `copilot-tier-basic-adopter` — For Basic Adopter tier users
   - `copilot-tier-growing-user` — For Growing User tier users
   - `copilot-tier-power-user` — For Power User tier users
   - `copilot-tier-advanced-user` — For Advanced User tier users

   Use: `POST /enterprises/{enterprise}/settings/billing/cost-centers` with `-f name="copilot-tier-{tier}"`

2. **Budgets** (optional, per cost center):
   - Basic Adopter: no budget needed (within included allowance)
   - Growing User: alert-only budget to monitor overage spend
   - Power User: no budget needed (Enterprise plan)
   - Advanced User: alert-only or hard cap budget for overage control

   Use: `POST /enterprises/{enterprise}/settings/billing/budgets`

## Output Required
At the end, provide:
- The 4 Cost Center IDs
- Any budget IDs created
- Confirmation that cost centers are visible in the enterprise billing dashboard
