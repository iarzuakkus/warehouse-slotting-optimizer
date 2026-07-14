"""Sipariş üst bilgisi endpoint testleri."""

from fastapi.testclient import TestClient


def create_order(db_client: TestClient, order_number: str) -> dict[str, object]:
    response = db_client.post(
        "/orders",
        json={
            "order_number": order_number,
            "ordered_at": None,
            "due_at": None,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_order_uses_database_defaults(db_client: TestClient) -> None:
    response = db_client.post(
        "/orders",
        json={
            "order_number": "test-order-001",
            "ordered_at": None,
            "due_at": None,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["order_number"] == "TEST-ORDER-001"
    assert body["status"] == "pending"
    assert body["ordered_at"] is not None
    assert body["due_at"] is None


def test_create_order_rejects_duplicate_number(db_client: TestClient) -> None:
    first_response = db_client.post(
        "/orders",
        json={"order_number": "test-order-002"},
    )
    duplicate_response = db_client.post(
        "/orders",
        json={"order_number": "TEST-ORDER-002"},
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409


def test_create_order_rejects_invalid_date_range(db_client: TestClient) -> None:
    response = db_client.post(
        "/orders",
        json={
            "order_number": "TEST-ORDER-003",
            "ordered_at": "2026-07-15T10:00:00+03:00",
            "due_at": "2026-07-14T10:00:00+03:00",
        },
    )

    assert response.status_code == 422


def test_order_status_lifecycle(db_client: TestClient) -> None:
    order = create_order(db_client, "TEST-ORDER-004")
    order_id = order["id"]

    allocated_response = db_client.patch(
        f"/orders/{order_id}",
        json={"status": "allocated"},
    )
    picking_response = db_client.patch(
        f"/orders/{order_id}",
        json={"status": "picking"},
    )
    completed_response = db_client.patch(
        f"/orders/{order_id}",
        json={"status": "completed"},
    )
    invalid_response = db_client.patch(
        f"/orders/{order_id}",
        json={"status": "cancelled"},
    )

    assert allocated_response.status_code == 200
    assert allocated_response.json()["status"] == "allocated"
    assert picking_response.status_code == 200
    assert picking_response.json()["status"] == "picking"
    assert completed_response.status_code == 200
    assert completed_response.json()["status"] == "completed"
    assert invalid_response.status_code == 409


def test_list_orders_filters_status(db_client: TestClient) -> None:
    pending_order = create_order(db_client, "TEST-ORDER-005")
    cancelled_order = create_order(db_client, "TEST-ORDER-006")
    cancel_response = db_client.patch(
        f"/orders/{cancelled_order['id']}",
        json={"status": "cancelled"},
    )
    assert cancel_response.status_code == 200

    response = db_client.get("/orders", params={"status": "pending"})

    assert response.status_code == 200
    result_ids = {item["id"] for item in response.json()}
    assert pending_order["id"] in result_ids
    assert cancelled_order["id"] not in result_ids
