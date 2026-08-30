from frontend.utils.presentation import format_activity_details, resolve_user_identity


def test_identity_uses_oidc_profile_when_api_claims_are_minimal() -> None:
    display_name, email = resolve_user_identity(
        {"display_name": None, "email": None},
        {"name": "Mayank Vyas", "email": "mayank@example.com"},
    )

    assert display_name == "Mayank Vyas"
    assert email == "mayank@example.com"


def test_identity_has_safe_fallbacks() -> None:
    assert resolve_user_identity({}, {"nickname": "mayank"}) == ("mayank", None)
    assert resolve_user_identity({}, {}) == ("User", None)


def test_activity_details_are_readable_and_hide_internal_ids() -> None:
    rendered = format_activity_details(
        {
            "assistant_message_id": "internal-uuid",
            "citation_count": 8,
            "target_type": "documents",
            "unused": None,
        }
    )

    assert rendered == "Citations: 8 · Scope: documents"
    assert "internal-uuid" not in rendered
