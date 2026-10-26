import pytest
from sqlalchemy import inspect, text

from tests.conftest import ADMIN_ID, USER_ID, image_bytes, service_headers, tma_header

ADMIN = {"Authorization": tma_header(ADMIN_ID)}
USER = {"Authorization": tma_header(USER_ID)}


def upload(name="Lamp", content=None, filename="photo.png", content_type="image/png"):
    return {
        "data": {"name": name},
        "files": {"image": (filename, image_bytes() if content is None else content, content_type)},
    }


async def create(client, headers=ADMIN, **kwargs):
    return await client.post("/api/v1/products", headers=headers, **upload(**kwargs))


async def test_listing_requires_authentication(client):
    assert (await client.get("/api/v1/products")).status_code == 401


async def test_user_sees_empty_catalog(client):
    response = await client.get("/api/v1/products", headers=USER)
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_offset": None}


async def test_user_cannot_create_products(client, storage):
    response = await create(client, headers=USER)
    assert response.status_code == 403
    assert storage.objects == {}


async def test_admin_creates_product_visible_to_users(client, storage):
    response = await create(client, name="  Desk   lamp \n")
    assert response.status_code == 201
    product = response.json()
    assert product["name"] == "Desk lamp"
    assert product["image_url"].startswith("https://cdn.test/products/")

    [(key, (payload, content_type))] = storage.objects.items()
    assert key.endswith(".png")
    assert content_type == "image/png"
    assert payload == image_bytes()

    listing = (await client.get("/api/v1/products", headers=USER)).json()
    assert [item["id"] for item in listing["items"]] == [product["id"]]


async def test_bot_service_credential_creates_for_admin_only(client):
    assert (await create(client, headers=service_headers(ADMIN_ID))).status_code == 201
    assert (await create(client, headers=service_headers(USER_ID))).status_code == 403


async def test_products_are_listed_newest_first_with_pagination(client):
    for name in ("first", "second", "third"):
        assert (await create(client, name=name)).status_code == 201

    page = (await client.get("/api/v1/products?limit=2", headers=USER)).json()
    assert [item["name"] for item in page["items"]] == ["third", "second"]
    assert page["next_offset"] == 2

    rest = (await client.get("/api/v1/products?limit=2&offset=2", headers=USER)).json()
    assert [item["name"] for item in rest["items"]] == ["first"]
    assert rest["next_offset"] is None


@pytest.mark.parametrize(
    "name",
    [
        "Robert'); DROP TABLE products;--",
        "' OR '1'='1",
        "lamp\"; DELETE FROM users WHERE ''='",
        "1; SELECT pg_sleep(10)",
    ],
)
async def test_sql_like_names_are_stored_as_plain_text(client, engine, name):
    response = await create(client, name=name)
    assert response.status_code == 201
    assert response.json()["name"] == name

    listing = (await client.get("/api/v1/products", headers=USER)).json()
    assert [item["name"] for item in listing["items"]] == [name]

    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
        users = (await connection.execute(text("SELECT count(*) FROM users"))).scalar_one()
    assert {"users", "products"} <= set(tables)
    assert users == 2


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "limit=abc",
        "limit=1;DROP TABLE products",
        "offset=-1",
        "offset=10001",
        "offset=0 OR 1=1",
    ],
)
async def test_invalid_pagination_is_rejected(client, query):
    response = await client.get(f"/api/v1/products?{query}", headers=USER)
    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid request"


async def test_unknown_sort_and_filter_parameters_are_ignored(client):
    await create(client, name="only")
    response = await client.get(
        "/api/v1/products?sort=name;DROP TABLE products&order=desc&name=x' OR '1'='1",
        headers=USER,
    )
    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == ["only"]


@pytest.mark.parametrize(
    ("kwargs", "status"),
    [
        ({"content": b"not an image", "content_type": "image/png"}, 415),
        ({"content": image_bytes("GIF"), "filename": "a.gif", "content_type": "image/gif"}, 415),
        ({"content": b"<svg xmlns='http://www.w3.org/2000/svg'/>", "content_type": "image/svg+xml"}, 415),
        ({"content": image_bytes("PNG")[:40]}, 415),
        ({"content": b""}, 415),
        ({"content": image_bytes("BMP"), "content_type": "image/png"}, 415),
        ({"content": b"\x89PNG" + b"0" * 250_000}, 413),
        ({"content": image_bytes("PNG", (3000, 3000))}, 413),
        ({"name": "   "}, 422),
        ({"name": "x" * 121}, 422),
        ({"name": "bad\x00name"}, 422),
    ],
)
async def test_invalid_uploads_are_rejected(client, storage, kwargs, status):
    response = await create(client, **kwargs)
    assert response.status_code == status
    assert storage.objects == {}


async def test_jpeg_and_webp_are_accepted_by_content_not_declared_type(client, storage):
    jpeg = await create(client, content=image_bytes("JPEG"), filename="x.bin", content_type="text/plain")
    webp = await create(client, content=image_bytes("WEBP"), content_type="application/octet-stream")
    assert (jpeg.status_code, webp.status_code) == (201, 201)
    assert sorted(content_type for _, content_type in storage.objects.values()) == ["image/jpeg", "image/webp"]


async def test_unexpected_multipart_fields_are_rejected(client, storage):
    extra_field = await client.post(
        "/api/v1/products",
        headers=ADMIN,
        data={"name": "Lamp", "creator_telegram_id": "1"},
        files={"image": ("a.png", image_bytes(), "image/png")},
    )
    extra_file = await client.post(
        "/api/v1/products",
        headers=ADMIN,
        data={"name": "Lamp"},
        files=[("image", ("a.png", image_bytes(), "image/png")), ("image", ("b.png", image_bytes(), "image/png"))],
    )
    missing_image = await client.post("/api/v1/products", headers=ADMIN, files={"name": (None, "Lamp")})
    json_body = await client.post("/api/v1/products", headers=ADMIN, json={"name": "Lamp"})

    assert extra_field.status_code == 400
    assert extra_file.status_code == 400
    assert missing_image.status_code == 422
    assert json_body.status_code == 415
    assert storage.objects == {}


async def test_declared_oversized_body_is_rejected_before_parsing(client):
    response = await client.post(
        "/api/v1/products",
        headers={**ADMIN, "Content-Type": "multipart/form-data; boundary=x", "Content-Length": "999999999"},
        content=b"",
    )
    assert response.status_code == 413


async def test_uploaded_object_is_removed_when_database_write_fails(client, engine, storage):
    await client.get("/api/v1/auth/me", headers=ADMIN)
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE products"))

    response = await create(client)

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert body["request_id"] == response.headers["x-request-id"]
    assert "products" not in response.text.lower()
    assert storage.objects == {}


async def test_responses_carry_security_headers(client):
    response = await client.get("/api/v1/products", headers=USER)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]


async def test_docs_are_hidden_in_production(client):
    assert (await client.get("/api/docs")).status_code == 404
    assert (await client.get("/api/openapi.json")).status_code == 404
