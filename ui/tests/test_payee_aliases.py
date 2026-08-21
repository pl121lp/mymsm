import json

from payee_aliases import (
    apply_aliases,
    load_aliases,
    load_canonical_names,
    merge_groups,
    resolve_payee_ids,
    save_aliases,
)


def test_load_aliases_missing_file_returns_empty(tmp_path):
    assert load_aliases(tmp_path / "missing.json") == {}
    assert load_canonical_names(tmp_path / "missing.json") == {}


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "payee_aliases.json"
    save_aliases({100: [101, 102]}, {100: "4S Ranch Master Assn"}, path=path)

    assert load_aliases(path) == {100: [101, 102]}
    assert load_canonical_names(path) == {100: "4S Ranch Master Assn"}


def test_saved_file_is_readable_json_with_string_keys(tmp_path):
    path = tmp_path / "payee_aliases.json"
    save_aliases({100: [101, 102]}, {100: "4S Ranch Master Assn"}, path=path)

    raw = json.loads(path.read_text())
    assert raw["groups"]["100"] == [101, 102]
    assert raw["names"]["100"] == "4S Ranch Master Assn"


def test_merge_groups_unions_members_for_shared_canonical():
    existing = {100: [101]}
    additional = {100: [102], 200: [201]}
    assert merge_groups(existing, additional) == {100: [101, 102], 200: [201]}


def test_merge_groups_does_not_duplicate_already_present_member():
    existing = {100: [101]}
    additional = {100: [101, 102]}
    assert merge_groups(existing, additional) == {100: [101, 102]}


def test_apply_aliases_drops_absorbed_rows_and_keeps_canonical():
    payees = [(100, "Bravo Canonical"), (101, "4s ranch"), (200, "Alpha Unrelated")]
    result = apply_aliases(payees, groups={100: [101]})
    assert result == [
        (200, "Alpha Unrelated"),
        (100, "Bravo Canonical"),
    ]


def test_apply_aliases_uses_name_override_for_canonical():
    payees = [(100, "Withdrawal 4S Ranch Master Id"), (101, "4s ranch")]
    result = apply_aliases(
        payees, groups={100: [101]}, names={100: "4S Ranch Master Assn"}
    )
    assert result == [(100, "4S Ranch Master Assn")]


def test_apply_aliases_with_no_groups_is_a_passthrough():
    payees = [(200, "Bravo"), (100, "Alpha")]
    assert apply_aliases(payees, groups={}) == [(100, "Alpha"), (200, "Bravo")]


def test_resolve_payee_ids_for_canonical_returns_all_members():
    assert resolve_payee_ids(100, groups={100: [101, 102]}) == [100, 101, 102]


def test_resolve_payee_ids_for_standalone_payee_returns_itself():
    assert resolve_payee_ids(200, groups={100: [101, 102]}) == [200]
