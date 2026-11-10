"""
Synora Security Audit Verification Script
Tests all backend API endpoints for authentication, authorization, multi-tenant organization isolation,
and sanitized health diagnostics.
Runs against the live backend at http://localhost:8000.
Never prints secrets or tokens.
"""
import sys
import json
import http.client
import urllib.parse
import uuid

BASE_HOST = "127.0.0.1"
BASE_PORT = 8000
API_PREFIX = "/api/v1"

RESULTS = []
PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


def req(method, path, body=None, token=None, content_type="application/json"):
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=15)
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    encoded_body = json.dumps(body).encode() if body else None
    try:
        conn.request(method, f"{API_PREFIX}{path}", body=encoded_body, headers=headers)
        r = conn.getresponse()
        try:
            data = json.loads(r.read())
        except Exception:
            data = {}
        return r.status, data
    except Exception as e:
        return 0, {"error": str(e)}
    finally:
        conn.close()


def check(name, status_code, expected_codes, detail=""):
    result = PASS if status_code in expected_codes else FAIL
    RESULTS.append((result, name, status_code, expected_codes, detail))
    marker = "✓" if result == PASS else "✗"
    print(f"[{result}] {marker} {name}: HTTP {status_code} (expected {expected_codes}) {detail}")
    return result == PASS


# ─────────────────────────────────────────────────────────
# Step 1: Register two users in different organizations
# ─────────────────────────────────────────────────────────
uid = uuid.uuid4().hex[:6]
print(f"\n{'='*60}\nStep 1: Registering test users (uid={uid})\n{'='*60}")

# Manager in Org A
code, data = req("POST", "/auth/register", {
    "email": f"mgr_a_{uid}@test.corp",
    "password": "TestPassword123!",
    "full_name": f"Manager A {uid}",
    "role": "manager",
    "organization_name": f"OrgAlpha-{uid}",
})
print(f"Register Manager A: HTTP {code}")
if code != 201 or "access_token" not in data:
    print("FATAL: Could not register Manager A. Is backend running at port 8000?")
    sys.exit(1)
TOKEN_MGR_A = data["access_token"]
ORG_A_ID = data["user"]["organization_id"]

# Employee in Org A
code, data = req("POST", "/auth/register", {
    "email": f"emp_a_{uid}@test.corp",
    "password": "TestPassword123!",
    "full_name": f"Employee A {uid}",
    "role": "employee",
    "organization_name": f"OrgAlpha-{uid}",
})
print(f"Register Employee A: HTTP {code}")
TOKEN_EMP_A = data.get("access_token")
EMP_A_ID = data.get("user", {}).get("id")

# Manager in Org B (different org)
code, data = req("POST", "/auth/register", {
    "email": f"mgr_b_{uid}@test.corp",
    "password": "TestPassword123!",
    "full_name": f"Manager B {uid}",
    "role": "manager",
    "organization_name": f"OrgBeta-{uid}",
})
print(f"Register Manager B: HTTP {code}")
TOKEN_MGR_B = data.get("access_token")
ORG_B_ID = data.get("user", {}).get("organization_id")

# Employee in Org B
code, data = req("POST", "/auth/register", {
    "email": f"emp_b_{uid}@test.corp",
    "password": "TestPassword123!",
    "full_name": f"Employee B {uid}",
    "role": "employee",
    "organization_name": f"OrgBeta-{uid}",
})
print(f"Register Employee B: HTTP {code}")
TOKEN_EMP_B = data.get("access_token")
EMP_B_ID = data.get("user", {}).get("id")

# ─────────────────────────────────────────────────────────
# Step 2: Authentication Tests
# ─────────────────────────────────────────────────────────
print(f"\n{'='*60}\nStep 2: Authentication & Token Tests\n{'='*60}")

# 2.1 /auth/me requires auth
code, _ = req("GET", "/auth/me")
check("/auth/me (no token) → 401", code, [401])

# 2.2 /auth/me with valid token → 200
code, data = req("GET", "/auth/me", token=TOKEN_MGR_A)
check("/auth/me (valid manager token) → 200", code, [200])

# 2.3 /auth/me MUST NOT expose password hash
has_pw = "hashed_password" in str(data) or "password" in str(data).lower() and "token" not in str(data).lower()
check("/auth/me response has no password field", 200 if not has_pw else 0, [200])

# 2.4 Invalid JWT → 401
code, _ = req("GET", "/auth/me", token="invalid.bearer.token")
check("/auth/me (invalid JWT) → 401", code, [401])

# 2.5 Login with wrong password → 401
code, data = req("POST", "/auth/login", {
    "email": f"mgr_a_{uid}@test.corp",
    "password": "WRONG_PASSWORD_999"
})
check("/auth/login (wrong password) → 401", code, [401])

# 2.6 Anonymous access to sensitive handover list → 401
code, _ = req("GET", "/handovers/")
check("GET /handovers/ (unauthenticated) → 401", code, [401])

# 2.7 Anonymous access to sensitive handover detail → 401
code, _ = req("GET", "/handovers/ho-101")
check("GET /handovers/{id} (unauthenticated) → 401", code, [401])

# ─────────────────────────────────────────────────────────
# Step 3: Handover Creation & Scoping
# ─────────────────────────────────────────────────────────
print(f"\n{'='*60}\nStep 3: Handover Creation & Scoping\n{'='*60}")

# Create an unlinked handover as Employee A in Org A
code, hw_data = req("POST", "/handovers/", {
    "employee_name": f"Employee A {uid}",
    "role": "Senior Engineer",
    "department": "Platform",
    "transition_type": "resignation",
    "project_name": f"Critical Infra {uid}",
    "key_responsibilities": ["Primary On-Call", "TLS Cert Rotation"],
    "completed_tasks": ["Migrated DB to Supabase"],
    "pending_tasks": ["Handover keys"],
}, token=TOKEN_EMP_A)
print(f"Create handover as Employee A: HTTP {code}")
check("Create handover populates successfully → 201", code, [201])
HANDOVER_ID = hw_data.get("id")
HW_ORG_ID = hw_data.get("organization_id")
check("Handover organization_id automatically populated", 200 if HW_ORG_ID == ORG_A_ID else 0, [200],
      f"(expected {ORG_A_ID}, got {HW_ORG_ID})")

# Submit handover so it moves to 'submitted'
code, sub_data = req("POST", f"/handovers/{HANDOVER_ID}/submit", {
    "actor_name": f"Employee A {uid}"
}, token=TOKEN_EMP_A)
check("Submit handover → 200 (status=submitted)", code, [200])

# ─────────────────────────────────────────────────────────
# Step 4: Role-Based Authorization Tests
# ─────────────────────────────────────────────────────────
print(f"\n{'='*60}\nStep 4: Role-Based Authorization Tests\n{'='*60}")

# 4.1 Employee cannot start review (manager-only)
code, _ = req("POST", f"/handovers/{HANDOVER_ID}/start-review", {}, token=TOKEN_EMP_A)
check("/handovers/start-review (employee) → 403", code, [403])

# 4.2 Employee cannot approve (manager-only)
code, _ = req("POST", f"/handovers/{HANDOVER_ID}/approve", {}, token=TOKEN_EMP_A)
check("/handovers/approve (employee) → 403", code, [403])

# 4.3 Employee cannot assign (manager-only)
code, _ = req("POST", f"/handovers/{HANDOVER_ID}/assign", {"assigned_to": EMP_A_ID}, token=TOKEN_EMP_A)
check("/handovers/assign (employee) → 403", code, [403])

# 4.4 Employee cannot list eligible assignees (manager-only)
code, _ = req("GET", "/handovers/assignees", token=TOKEN_EMP_A)
check("/handovers/assignees (employee) → 403", code, [403])

# 4.5 Manager A in Org A can list eligible assignees in Org A
code, assignees_data = req("GET", "/handovers/assignees", token=TOKEN_MGR_A)
check("/handovers/assignees (manager) → 200", code, [200])
assignee_ids = [u.get("id") for u in (assignees_data if isinstance(assignees_data, list) else [])]
check("Org A assignees include Employee A", 200 if EMP_A_ID in assignee_ids else 0, [200])
check("Org A assignees DO NOT include Org B Employee", 200 if EMP_B_ID not in assignee_ids else 0, [200])

# 4.6 Employee cannot remediate sentinel risks (manager-only)
code, _ = req("PATCH", "/sentinel/risks/fake-id", {"action": "resolve", "notes": "test"}, token=TOKEN_EMP_A)
check("/sentinel/risks PATCH (employee) → 403 or 404", code, [403, 404])

# 4.7 Employee cannot remediate radar risks (manager-only)
code, _ = req("PATCH", "/radar/risks/fake-id", {"notes": "test"}, token=TOKEN_EMP_A)
check("/radar/risks PATCH (employee) → 403 or 404", code, [403, 404])

# 4.8 Employee cannot verify knowledge nodes (manager-only)
code, _ = req("PATCH", "/knowledge/nodes/fake-id/verify", {
    "action": "verified", "reviewer_name": "emp"
}, token=TOKEN_EMP_A)
check("/knowledge/nodes/verify PATCH (employee) → 403 or 404", code, [403, 404])

# ─────────────────────────────────────────────────────────
# Step 5: Multi-Tenant Cross-Organization Isolation Tests
# ─────────────────────────────────────────────────────────
print(f"\n{'='*60}\nStep 5: Multi-Tenant Cross-Organization Isolation Tests\n{'='*60}")

# 5.1 Manager B (Org B) cannot GET Org A's handover
code, _ = req("GET", f"/handovers/{HANDOVER_ID}", token=TOKEN_MGR_B)
check("Org B manager cannot GET Org A handover → 403", code, [403])

# 5.2 Employee B (Org B) cannot GET Org A's handover
code, _ = req("GET", f"/handovers/{HANDOVER_ID}", token=TOKEN_EMP_B)
check("Org B employee cannot GET Org A handover → 403", code, [403])

# 5.3 Manager B cannot assign Org A's handover
code, _ = req("POST", f"/handovers/{HANDOVER_ID}/assign", {
    "assigned_to": EMP_B_ID
}, token=TOKEN_MGR_B)
check("Org B manager cannot assign Org A handover → 403", code, [403])

# 5.4 Manager A cannot assign Org A's handover to an employee from Org B
code, _ = req("POST", f"/handovers/{HANDOVER_ID}/assign", {
    "assigned_to": EMP_B_ID
}, token=TOKEN_MGR_A)
check("Cross-org assignment to external employee rejected → 403", code, [403])

# 5.5 Manager B's handover list does NOT contain Org A's handover
code, list_b = req("GET", "/handovers/", token=TOKEN_MGR_B)
check("Manager B list handovers → 200", code, [200])
b_ids = [h.get("id") for h in (list_b if isinstance(list_b, list) else [])]
check("Manager B list excludes Org A handover", 200 if HANDOVER_ID not in b_ids else 0, [200])

# 5.6 Manager A's handover list DOES contain Org A's handover
code, list_a = req("GET", "/handovers/", token=TOKEN_MGR_A)
a_ids = [h.get("id") for h in (list_a if isinstance(list_a, list) else [])]
check("Manager A list includes Org A handover", 200 if HANDOVER_ID in a_ids else 0, [200])

# ─────────────────────────────────────────────────────────
# Step 6: Valid Intra-Organization Assignment Workflow
# ─────────────────────────────────────────────────────────
print(f"\n{'='*60}\nStep 6: Valid Intra-Organization Assignment Workflow\n{'='*60}")

# Manager A assigns Handover A to Employee A
code, assign_res = req("POST", f"/handovers/{HANDOVER_ID}/assign", {
    "assigned_to": EMP_A_ID,
    "notes": "Assigned for onboarding validation."
}, token=TOKEN_MGR_A)
check("Manager A assigns handover to Employee A → 200", code, [200])
check("Assignee ID matches Employee A", 200 if assign_res.get("assigned_to") == EMP_A_ID else 0, [200])

# Assigned Employee A can access the assigned handover
code, emp_access = req("GET", f"/handovers/{HANDOVER_ID}", token=TOKEN_EMP_A)
check("Assigned Employee A retrieves handover → 200", code, [200])

# Filter by assigned_to=me returns this handover for Employee A
code, my_handovers = req("GET", "/handovers/?assigned_to=me", token=TOKEN_EMP_A)
check("Employee A GET /handovers/?assigned_to=me → 200", code, [200])
my_ids = [h.get("id") for h in (my_handovers if isinstance(my_handovers, list) else [])]
check("Handover present in Employee A assigned list", 200 if HANDOVER_ID in my_ids else 0, [200])

# ─────────────────────────────────────────────────────────
# Step 7: Health Endpoint Diagnostics & Secret Exposure Audit
# ─────────────────────────────────────────────────────────
print(f"\n{'='*60}\nStep 7: Health Endpoint Diagnostics & Secret Exposure Audit\n{'='*60}")

code, health_data = req("GET", "/health")
check("GET /health public endpoint → 200", code, [200])
check("Health status is healthy", 200 if health_data.get("status") == "healthy" else 0, [200])
check("Database reports connected", 200 if health_data.get("database") == "connected" else 0, [200])

# Verify NO secrets, NO hostnames, NO credentials, NO pool status in public /health
sensitive_keywords = [
    "password",
    "sb_secret",
    "service_role",
    "secret_key",
    "postgresql+psycopg",
    "aws-1-ap",
    "supabase.com",
    "pool_status",
    "checked_in",
    "checked_out",
    "postgres.cicmhudjibrnqintajnq",
]
health_str = json.dumps(health_data).lower()
leaked = [kw for kw in sensitive_keywords if kw.lower() in health_str]
check("Public /health reveals zero secrets or internal hostnames",
      200 if not leaked else 0, [200],
      f"LEAKED: {leaked}" if leaked else "(completely sanitized)")

# Check database_target is abstract
target_val = health_data.get("database_target")
check("database_target is abstract (managed-cloud or local)",
      200 if target_val in ["managed-cloud", "local"] else 0, [200],
      f"(got: {target_val})")

# 7.2 Authenticated internal diagnostics
code, diag_data = req("GET", "/health/diagnostics", token=TOKEN_MGR_A)
check("GET /health/diagnostics (authenticated manager) → 200", code, [200])
code, _ = req("GET", "/health/diagnostics")
check("GET /health/diagnostics (unauthenticated) → 401", code, [401])

# ─────────────────────────────────────────────────────────
# Step 8: Document & Storage Authorization Tests
# ─────────────────────────────────────────────────────────
print(f"\n{'='*60}\nStep 8: Document & Storage Authorization Tests\n{'='*60}")

# Download non-existent document
code, _ = req("GET", "/documents/nonexistent-doc/download", token=TOKEN_MGR_A)
check("/documents/nonexistent-doc/download → 404", code, [404])

# Delete non-existent document
code, _ = req("DELETE", "/documents/nonexistent-doc", token=TOKEN_MGR_A)
check("/documents/nonexistent-doc DELETE → 404", code, [404])

# ─────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────
print(f"\n{'='*60}\nAUDIT SUMMARY\n{'='*60}")
passed = sum(1 for r in RESULTS if r[0] == PASS)
failed = sum(1 for r in RESULTS if r[0] == FAIL)
warned = sum(1 for r in RESULTS if r[0] == WARN)
total = len(RESULTS)
print(f"Total Checks: {total} | Passed: {passed} | Failed: {failed} | Warnings: {warned}")

failures = [(r[1], r[2], r[3], r[4]) for r in RESULTS if r[0] == FAIL]
if failures:
    print("\nFAILURES:")
    for name, code, expected, detail in failures:
        print(f"  ✗ {name}: HTTP {code} expected {expected}  {detail}")

sys.exit(0 if failed == 0 else 1)
