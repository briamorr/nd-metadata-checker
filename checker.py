"""Fetch Nexus Dashboard metadata downloads from Cisco Intersight and diff them."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import intersight
from intersight.api import search_api
from intersight.signing import (
    ALGORITHM_ECDSA_MODE_FIPS_186_3,
    HASH_SHA256,
    HEADER_DATE,
    HEADER_DIGEST,
    HEADER_HOST,
    HEADER_REQUEST_TARGET,
    SCHEME_HS2019,
    SCHEME_RSA_SHA256,
    HttpSigningConfiguration,
)

DEFAULT_HOST = "https://us-east-1.intersight.com"
ND_FILTER = "ObjectType eq 'niaapi.NdMetadataSoftwareDownload'"
# Display name -> SDK model attribute
FIELDS = {
    "Description": "description",
    "Name": "name",
    "ReleaseDate": "release_date",
    "Version": "version",
}
PAGE_SIZE = 100
KEY_FIELD = "Name"
COMPARE_FIELDS = ("ReleaseDate", "Version", "Description")


@contextmanager
def _secret_key_path(secret_key_file: Path):
    """Yield a path to the secret key, materializing INTERSIGHT_SECRET_KEY if set."""
    pem = os.environ.get("INTERSIGHT_SECRET_KEY")
    if not pem:
        yield secret_key_file
        return

    handle = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
    try:
        os.chmod(handle.name, 0o600)
        handle.write(pem if pem.endswith("\n") else pem + "\n")
        handle.close()
        yield Path(handle.name)
    finally:
        os.unlink(handle.name)


def build_client(
    host: str, api_key_file: Path, secret_key_file: Path
) -> intersight.ApiClient:
    key_id = os.environ.get("INTERSIGHT_API_KEY_ID") or api_key_file.read_text()
    with _secret_key_path(secret_key_file) as key_path:
        is_rsa = "RSA PRIVATE KEY" in key_path.read_text()
        signing = HttpSigningConfiguration(
            key_id=key_id.strip(),
            private_key_path=str(key_path),
            signing_scheme=SCHEME_RSA_SHA256 if is_rsa else SCHEME_HS2019,
            hash_algorithm=HASH_SHA256,
            signed_headers=[
                HEADER_REQUEST_TARGET,
                HEADER_HOST,
                HEADER_DATE,
                HEADER_DIGEST,
            ],
        )
        if not is_rsa:
            signing.signing_algorithm = ALGORITHM_ECDSA_MODE_FIPS_186_3
        return intersight.ApiClient(
            intersight.Configuration(host=host, signing_info=signing)
        )


def fetch_downloads(client: intersight.ApiClient) -> list[dict]:
    api = search_api.SearchApi(client)
    rows: list[dict] = []
    skip = 0

    while True:
        page = (
            api.get_search_search_item_list(
                filter=ND_FILTER,
                orderby="ModTime desc",
                top=PAGE_SIZE,
                skip=skip,
            ).results
            or []
        )
        rows.extend(
            {label: str(item.to_dict().get(attr) or "") for label, attr in FIELDS.items()}
            for item in page
        )
        if len(page) < PAGE_SIZE:
            return rows
        skip += PAGE_SIZE


def diff_downloads(previous: list[dict] | None, current: list[dict]) -> dict:
    """Compare two result sets keyed by Name."""
    old = {row.get(KEY_FIELD): row for row in previous or []}
    new = {row.get(KEY_FIELD): row for row in current}

    added = [new[name] for name in new if name not in old]
    removed = [old[name] for name in old if name not in new]
    updated = [
        {
            "current": new[name],
            "previous": old[name],
            "fields": [f for f in COMPARE_FIELDS if new[name].get(f) != old[name].get(f)],
        }
        for name in new
        if name in old
        and any(new[name].get(f) != old[name].get(f) for f in COMPARE_FIELDS)
    ]

    return {
        "added": added,
        "removed": removed,
        "updated": updated,
        "current": current,
        "first_run": previous is None,
        "changed": bool(added or removed or updated) or previous is None,
    }
