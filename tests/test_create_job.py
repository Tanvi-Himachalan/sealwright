"""Creating a generation job."""


def test_create_job_returns_202_and_job_details(client, job_payload):
    res = client.post("/api/jobs", json=job_payload)
    assert res.status_code == 202
    body = res.json()
    assert body["total"] == 3
    assert body["title"] == "Python Bootcamp 2026"
    assert body["links"]["certificates"] == f"/api/jobs/{body['id']}/certificates"


def test_single_request_handles_many_recipients(client):
    payload = {
        "title": "Mass Workshop", "issuer": "Org",
        "recipients": [{"name": f"Person Number{i}"} for i in range(60)],
    }
    body = client.post("/api/jobs", json=payload).json()
    assert body["total"] == 60
    assert body["counts"]["generated"] == 60


def test_get_unknown_job_is_404(client):
    assert client.get("/api/jobs/does-not-exist").status_code == 404


def test_csv_upload_creates_job(client):
    csv_bytes = "Full Name,E-mail,Remarks\nTanvi Sharma,t@example.com,Top scorer\nArjun Mehta,,\n".encode()
    res = client.post(
        "/api/jobs/upload",
        data={"title": "CSV Course", "issuer": "Org"},
        files={"file": ("people.csv", csv_bytes, "text/csv")},
    )
    assert res.status_code == 202
    assert res.json()["counts"]["generated"] == 2


def test_csv_without_name_column_is_rejected(client):
    res = client.post(
        "/api/jobs/upload",
        data={"title": "CSV Course", "issuer": "Org"},
        files={"file": ("bad.csv", b"email\na@b.com\n", "text/csv")},
    )
    assert res.status_code == 422
