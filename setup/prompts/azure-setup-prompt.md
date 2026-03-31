# Azure / Entra ID Setup for Copilot Tier Manager

You are setting up the Azure / Entra ID infrastructure for the Copilot Tier Manager GitHub Action. You have access to `az` CLI (authenticated with admin permissions) and `gh` CLI (authenticated with enterprise admin scopes).

## What You Need to Create

1. **Azure App Registration** called `copilot-tier-manager` with a client secret
   - Grant Microsoft Graph API application permissions: `GroupMember.ReadWrite.All`, `User.Read.All`, `Group.ReadWrite.All`
   - Grant admin consent for all permissions

2. **4 Entra ID Security Groups** (mail-enabled = false, security-enabled = true):
   - `copilot-tier-basic-adopter` — Basic Adopter tier (0-299 PRUs)
   - `copilot-tier-growing-user` — Growing User tier (300-699 PRUs)
   - `copilot-tier-power-user` — Power User tier (700-999 PRUs)
   - `copilot-tier-advanced-user` — Advanced User tier (1000+ PRUs)

3. **Assign all 4 groups to the GitHub EMU OIDC Enterprise App** for SCIM provisioning:
   - Find the Enterprise App's service principal object ID
   - Find the "User" app role ID on the Enterprise App
   - Create appRoleAssignments for each group with the "User" role

4. **Trigger SCIM provisioning** to sync the groups to GitHub:
   - Find the synchronization job for the GitHub EMU Enterprise App
   - Start the sync job and wait for completion

5. **Create 4 GitHub Enterprise Teams** linked to the SCIM groups:
   - Query `GET /scim/v2/enterprises/{enterprise}/Groups` to get SCIM group IDs
   - Create each enterprise team with `POST /enterprises/{enterprise}/teams` including the `group_id` parameter
   - Use API version header: `X-GitHub-Api-Version: 2026-03-10`

6. **Assign Copilot seats to the enterprise teams**:
   - `POST /enterprises/{enterprise}/copilot/billing/selected_enterprise_teams`
   - Body: `{"selected_enterprise_teams":["copilot-tier-basic-adopter","copilot-tier-growing-user","copilot-tier-power-user","copilot-tier-advanced-user"]}`

## Output Required
At the end, provide:
- App Registration Client ID
- App Registration Client Secret (store securely)
- Azure Tenant ID
- The 4 Entra ID Group Object IDs
- Confirmation that SCIM sync completed
- Confirmation that Copilot seats were assigned
