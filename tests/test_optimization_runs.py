"""Optimizasyon çalışması takip endpoint testleri."""

from fastapi.testclient import TestClient


def create_run(db_client: TestClient, suffix: str) -> int:
    response = db_client.post(
        "/optimization-runs",
        json={
            "algorithm_name": f"Test Algorithm {suffix}",
            "parameters": {"population_size": 20, "generations": 10},
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_optimization_run_lifecycle(db_client: TestClient) -> None:
    run_id = create_run(db_client, "001")

    pending = db_client.get(f"/optimization-runs/{run_id}")
    running = db_client.patch(
        f"/optimization-runs/{run_id}",
        json={"status": "running"},
    )
    completed = db_client.patch(
        f"/optimization-runs/{run_id}",
        json={"status": "completed", "objective_value": "125.750000"},
    )

    assert pending.status_code == 200
    assert pending.json()["status"] == "pending"
    assert running.status_code == 200
    assert running.json()["status"] == "running"
    assert running.json()["started_at"] is not None
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["objective_value"] == "125.750000"
    assert completed.json()["completed_at"] is not None


def test_rejects_invalid_status_transition(db_client: TestClient) -> None:
    run_id = create_run(db_client, "002")

    response = db_client.patch(
        f"/optimization-runs/{run_id}",
        json={"status": "completed", "objective_value": 10},
    )

    assert response.status_code == 409


def test_failed_run_requires_error_message(db_client: TestClient) -> None:
    run_id = create_run(db_client, "003")
    start = db_client.patch(
        f"/optimization-runs/{run_id}",
        json={"status": "running"},
    )
    assert start.status_code == 200

    response = db_client.patch(
        f"/optimization-runs/{run_id}",
        json={"status": "failed"},
    )

    assert response.status_code == 409


def test_terminal_run_cannot_change(db_client: TestClient) -> None:
    run_id = create_run(db_client, "004")
    start = db_client.patch(
        f"/optimization-runs/{run_id}",
        json={"status": "running"},
    )
    finish = db_client.patch(
        f"/optimization-runs/{run_id}",
        json={"status": "failed", "error_message": "Test failure"},
    )
    assert start.status_code == 200
    assert finish.status_code == 200

    response = db_client.patch(
        f"/optimization-runs/{run_id}",
        json={"status": "cancelled"},
    )

    assert response.status_code == 409


def test_list_runs_filters_status(db_client: TestClient) -> None:
    pending_id = create_run(db_client, "005-PENDING")
    failed_id = create_run(db_client, "005-FAILED")
    start = db_client.patch(
        f"/optimization-runs/{failed_id}",
        json={"status": "running"},
    )
    fail = db_client.patch(
        f"/optimization-runs/{failed_id}",
        json={"status": "failed", "error_message": "Expected test failure"},
    )
    assert start.status_code == 200
    assert fail.status_code == 200

    response = db_client.get("/optimization-runs", params={"status": "failed"})
    returned_ids = {item["id"] for item in response.json()}

    assert response.status_code == 200
    assert failed_id in returned_ids
    assert pending_id not in returned_ids
