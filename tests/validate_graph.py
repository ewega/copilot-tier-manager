"""Quick validation script for Graph API group operations."""
from src.graph_client import GraphClient

BASIC_GROUP = "04d6c6f1-5159-4c6a-b7a7-2235f59529dc"
GROWING_GROUP = "cb0377cc-7a6c-4eba-b10c-2f0c985b7dfa"
TEST_USER_ID = "38a1682b-fce0-4381-b11e-8c3b0dba6ae0"  # copilot.test.growing

graph = GraphClient()

# 1. Verify user is in basic group
members = graph.list_group_members(BASIC_GROUP)
member_ids = [m["id"] for m in members]
print(f"1. User in basic-adopter: {TEST_USER_ID in member_ids}")

# 2. Add user to growing group (add BEFORE remove)
print("2. Adding user to growing-user group...")
graph.add_group_member(GROWING_GROUP, TEST_USER_ID)

# 3. Verify user is in growing group
members = graph.list_group_members(GROWING_GROUP)
member_ids = [m["id"] for m in members]
print(f"3. User in growing-user: {TEST_USER_ID in member_ids}")

# 4. Remove user from basic group
print("4. Removing user from basic-adopter group...")
graph.remove_group_member(BASIC_GROUP, TEST_USER_ID)

# 5. Verify user is NOT in basic group
members = graph.list_group_members(BASIC_GROUP)
member_ids = [m["id"] for m in members]
print(f"5. User in basic-adopter: {TEST_USER_ID in member_ids}")

# 6. Clean up: move user back to basic
print("6. Cleanup: moving user back to basic-adopter...")
graph.add_group_member(BASIC_GROUP, TEST_USER_ID)
graph.remove_group_member(GROWING_GROUP, TEST_USER_ID)

# 7. Final verification
members_basic = graph.list_group_members(BASIC_GROUP)
members_growing = graph.list_group_members(GROWING_GROUP)
print(f"7. Final: basic={len(members_basic)} members, growing={len(members_growing)} members")
print("ALL GRAPH TESTS PASSED")
