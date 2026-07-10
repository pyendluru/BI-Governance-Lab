from fastapi.testclient import TestClient

from bi_governance_lab.seed import seed


def test_governance_api_runs_and_lists_findings(configured_temp_db):
    session_factory = configured_temp_db
    seed()

    from bi_governance_lab.api.governance import get_session
    from bi_governance_lab.main import app

    def override_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)

        run_response = client.post("/governance/rules/run")
        assert run_response.status_code == 200
        run_payload = run_response.json()
        assert run_payload
        assert {
            "rule_id",
            "asset_id",
            "asset_type",
            "severity",
            "category",
            "finding",
            "recommendation",
            "evidence",
        } <= set(run_payload[0])

        findings_response = client.get("/governance/findings", params={"category": "refresh"})
        assert findings_response.status_code == 200
        findings_payload = findings_response.json()
        assert findings_payload
        assert {finding["category"] for finding in findings_payload} == {"refresh"}

        limited_response = client.get("/governance/findings", params={"limit": 2, "offset": 1})
        assert limited_response.status_code == 200
        assert len(limited_response.json()) == 2

        health_response = client.get("/health")
        assert health_response.status_code == 200
        assert health_response.json()["status"] == "ok"
    finally:
        app.dependency_overrides.clear()
