"""Optimizasyon yerleşim önerisi endpoint testleri."""

from fastapi.testclient import TestClient


def create_assignment_context(
    db_client: TestClient,
    suffix: str,
    start_run: bool = True,
) -> tuple[int, int, int, int]:
    product = db_client.post(
        "/products",
        json={
            "sku": f"TEST-ASSIGNMENT-PRODUCT-{suffix}",
            "name": "Yerlesim Onerisi Test Urunu",
            "is_active": True,
        },
    )
    carton_type = db_client.post(
        "/carton-types",
        json={
            "code": f"TEST-ASSIGNMENT-CT-{suffix}",
            "name": "Yerlesim Onerisi Test Tipi",
            "inner_length_cm": 40,
            "inner_width_cm": 30,
            "inner_height_cm": 25,
            "max_weight_kg": 20,
            "is_active": True,
        },
    )
    assert product.status_code == 201
    assert carton_type.status_code == 201

    packaging = db_client.post(
        "/product-packaging",
        json={
            "product_id": product.json()["id"],
            "carton_type_id": carton_type.json()["id"],
            "units_per_carton": 24,
            "is_default": True,
        },
    )
    assert packaging.status_code == 201

    location_ids: list[int] = []
    for label, slot in (("SOURCE", "01"), ("TARGET", "02")):
        location = db_client.post(
            "/warehouse-locations",
            json={
                "aisle": f"TEST-ASSIGNMENT-{suffix}-{label}",
                "bay": "01",
                "level": "01",
                "slot": slot,
                "distance_from_dispatch_m": 10,
                "is_active": True,
            },
        )
        assert location.status_code == 201
        location_ids.append(location.json()["id"])

    carton = db_client.post(
        "/cartons",
        json={
            "carton_number": f"TEST-ASSIGNMENT-CARTON-{suffix}",
            "product_packaging_id": packaging.json()["id"],
            "current_location_id": location_ids[0],
            "current_qty": 20,
        },
    )
    run = db_client.post(
        "/optimization-runs",
        json={
            "algorithm_name": f"Assignment Test Algorithm {suffix}",
            "parameters": {},
        },
    )
    assert carton.status_code == 201
    assert run.status_code == 201

    run_id = run.json()["id"]
    if start_run:
        start = db_client.patch(
            f"/optimization-runs/{run_id}",
            json={"status": "running"},
        )
        assert start.status_code == 200

    return run_id, carton.json()["id"], location_ids[0], location_ids[1]


def test_optimization_assignment_lifecycle(db_client: TestClient) -> None:
    run_id, carton_id, source_id, target_id = create_assignment_context(
        db_client,
        "001",
    )
    url = f"/optimization-runs/{run_id}/assignments"

    create_response = db_client.post(
        url,
        json={
            "carton_id": carton_id,
            "to_location_id": target_id,
            "assignment_score": "8.250000",
        },
    )
    assert create_response.status_code == 201
    assignment_id = create_response.json()["id"]

    list_response = db_client.get(url)
    detail_response = db_client.get(f"{url}/{assignment_id}")
    delete_response = db_client.delete(f"{url}/{assignment_id}")
    final_response = db_client.get(f"{url}/{assignment_id}")

    assert create_response.json()["from_location_id"] == source_id
    assert create_response.json()["to_location_id"] == target_id
    assert create_response.json()["assignment_score"] == "8.250000"
    assert [item["id"] for item in list_response.json()] == [assignment_id]
    assert detail_response.status_code == 200
    assert delete_response.status_code == 204
    assert final_response.status_code == 404


def test_rejects_duplicate_carton_assignment(db_client: TestClient) -> None:
    run_id, carton_id, _, target_id = create_assignment_context(db_client, "002")
    url = f"/optimization-runs/{run_id}/assignments"
    payload = {"carton_id": carton_id, "to_location_id": target_id}

    first = db_client.post(url, json=payload)
    duplicate = db_client.post(url, json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 409


def test_rejects_assignment_while_run_is_pending(db_client: TestClient) -> None:
    run_id, carton_id, _, target_id = create_assignment_context(
        db_client,
        "003",
        start_run=False,
    )

    response = db_client.post(
        f"/optimization-runs/{run_id}/assignments",
        json={"carton_id": carton_id, "to_location_id": target_id},
    )

    assert response.status_code == 409


def test_rejects_assignment_to_current_location(db_client: TestClient) -> None:
    run_id, carton_id, source_id, _ = create_assignment_context(db_client, "004")

    response = db_client.post(
        f"/optimization-runs/{run_id}/assignments",
        json={"carton_id": carton_id, "to_location_id": source_id},
    )

    assert response.status_code == 409


def test_completed_run_locks_assignments(db_client: TestClient) -> None:
    run_id, carton_id, _, target_id = create_assignment_context(db_client, "005")
    url = f"/optimization-runs/{run_id}/assignments"
    assignment = db_client.post(
        url,
        json={"carton_id": carton_id, "to_location_id": target_id},
    )
    assert assignment.status_code == 201

    complete = db_client.patch(
        f"/optimization-runs/{run_id}",
        json={"status": "completed", "objective_value": 10},
    )
    assert complete.status_code == 200

    response = db_client.delete(f"{url}/{assignment.json()['id']}")

    assert response.status_code == 409
