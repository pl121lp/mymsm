from payee_merge import find_merge_groups, normalize


def test_normalize_strips_digits_and_punctuation():
    assert normalize("CHEVRON 0371991 SAN DIEGO CA") == "CHEVRON SAN DIEGO CA"


def test_normalize_strips_generic_transaction_noise_words():
    assert normalize("Advance Amzn Mktp Us Amzn.Com/Bi") == "AMZN MKTP US AMZN BI"
    # digits are stripped even mid-token ("4S" -> "S"); harmless for
    # clustering since the transform is applied consistently to every variant
    assert normalize("Withdrawal 4S Ranch Master Id") == "S RANCH MASTER ID"


def test_normalize_returns_empty_string_for_pure_noise():
    assert normalize("0.500%") == ""


def test_finds_group_for_dues_statement_variants():
    payees = [
        (1, "4S Ranch Master  Assn Dues  2267"),
        (2, "4S Ranch Master  Assn Dues  2279"),
        (3, "4s ranch master association"),
        (4, "Withdrawal 4S Ranch Master Id"),
        (5, "Unrelated Payee"),
    ]
    groups = find_merge_groups(payees)
    assert len(groups) == 1
    group = groups[0]
    assert {m[0] for m in group.members} == {1, 2, 3, 4}
    assert 5 not in {m[0] for m in group.members}


def test_singleton_names_are_not_grouped():
    payees = [(1, "Unique Payee One"), (2, "Totally Different Store")]
    assert find_merge_groups(payees) == []


def test_canonical_name_prefers_variant_without_leading_noise_word():
    payees = [
        (1, "Withdrawal 4S Ranch Master Id"),
        (2, "4s ranch master association"),
    ]
    txn_counts = {1: 16, 2: 2}  # the noisy variant has far more transactions
    [group] = find_merge_groups(payees, txn_counts)
    assert group.canonical_payee_id == 2
    assert group.canonical_name == "4s ranch master association"


def test_canonical_name_prefers_variant_without_order_code_when_no_noise_word():
    payees = [
        (1, "AMZN Mktp US*M21UJ31C2 Amzn.com/"),
        (2, "AMZN Mktp US Amzn.com/billWA"),
    ]
    txn_counts = {1: 1, 2: 36}
    [group] = find_merge_groups(payees, txn_counts)
    assert group.canonical_payee_id == 2


def test_group_members_are_sorted_by_txn_count_descending():
    payees = [(1, "Subway 00280859 San Diego Ca"), (2, "Subway"), (3, "Subway 00271171 San Diego Ca")]
    txn_counts = {1: 2, 2: 26, 3: 15}
    [group] = find_merge_groups(payees, txn_counts)
    assert [m[0] for m in group.members] == [2, 3, 1]


def test_groups_are_sorted_largest_first():
    payees = [
        (1, "Subway"), (2, "Subway 00280859 San Diego Ca"),
        (3, "Starbucks Store 06661"), (4, "Starbucks Store 06943"), (5, "Starbucks Store 06848"),
    ]
    groups = find_merge_groups(payees)
    assert len(groups[0].members) >= len(groups[1].members)


def test_unrelated_merchants_sharing_advance_prefix_do_not_merge():
    payees = [
        (1, "Advance MCDONALD'S F11180 SA"),
        (2, "Advance SOUTHWES 5262493921 800-"),
    ]
    assert find_merge_groups(payees) == []
