"""A tenant is not a user. Conflating them empties the corpus.

`TenantContext` feeds the Qdrant server-side filter
(services/qdrant/searcher.py) and namespaces every cache tier. When an auth path
sets `tenant_id` to the user's own UUID, that user's requests filter doctrine on
a tenant no document carries — so retrieval returns nothing and every answer
abstains, while their cache namespace is unique so nothing is ever shared.

`get_tenant_id_from_user` carries a CRIT-P0 note against exactly this, but the
note only guards its own fallback: a caller handing it `tenant_id=<user uuid>`
sails straight through. Two auth paths did (found 2026-09-13).

This matters more as tenants multiply — "sri amma bhagavan" alongside
"sri preethaji and sri krishnaji" needs tenant to be a real, separate dimension.
"""

import inspect

from app.config import get_settings
from services import auth_service
from services.tenant_context import get_tenant_id_from_user


def test_no_auth_path_uses_the_user_id_as_tenant():
    src = inspect.getsource(auth_service)
    assert '"tenant_id": str(user.id)' not in src, (
        "the local auth path must not make each user their own tenant"
    )
    assert 'payload.get("tenant_id", user_id)' not in src, (
        "the JWT path must not fall back to `sub` as the tenant"
    )


def test_helper_still_refuses_to_invent_a_tenant_from_the_user():
    # No tenant claim at all -> shared default, never the user id.
    resolved = get_tenant_id_from_user({"id": "abc-123", "email": "x@y.z"})
    assert resolved != "abc-123"
    assert resolved


def test_real_tenant_claims_are_honoured():
    assert get_tenant_id_from_user({"id": "u1", "tenant_id": "amma-bhagavan"}) == "amma-bhagavan"
    assert (
        get_tenant_id_from_user({"id": "u1", "app_metadata": {"tenant_id": "oneness"}})
        == "oneness"
    )


def test_default_tenant_is_configured_not_derived():
    assert get_settings().default_tenant_id
