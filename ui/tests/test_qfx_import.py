from datetime import date
from decimal import Decimal

import pytest

from qfx_import import QfxRecord, parse_account_id, parse_qfx

SAMPLE_QFX = """
OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE
<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS>
<CODE>0
<SEVERITY>INFO
</STATUS>
<DTSERVER>20260821120000[0:GMT]
<LANGUAGE>ENG
<FI>
<ORG>B1
<FID>10898
</FI>
<INTU.BID>10898
</SONRS>
</SIGNONMSGSRSV1>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>1
<STATUS>
<CODE>0
<SEVERITY>INFO
<MESSAGE>Success
</STATUS>
<STMTRS>
<CURDEF>USD
<BANKACCTFROM>
<BANKID>322271627
<ACCTID>597883795
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20240821120000[0:GMT]
<DTEND>20260818120000[0:GMT]
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260818120000[0:GMT]
<TRNAMT>-1.99
<FITID>202608180
<NAME>PAYPAL           PURCHASE   GOOG
<MEMO>LE GOOGLE O WEB ID: PAYPALSI77
</STMTTRN>
<STMTTRN>
<TRNTYPE>CHECK
<DTPOSTED>20260406120000[0:GMT]
<TRNAMT>-250.00
<FITID>202604060
<CHECKNUM>129
<NAME>CHECK 129
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20260720120000[0:GMT]
<TRNAMT>0.28
<FITID>202607202
<NAME>INTEREST PAYMENT
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""


def test_parse_qfx_extracts_all_records(tmp_path):
    qfx_path = tmp_path / "sample.qfx"
    qfx_path.write_text(SAMPLE_QFX)

    records = parse_qfx(qfx_path)

    assert len(records) == 3


def test_parse_qfx_reads_debit_record_fields(tmp_path):
    qfx_path = tmp_path / "sample.qfx"
    qfx_path.write_text(SAMPLE_QFX)

    record = parse_qfx(qfx_path)[0]

    assert record == QfxRecord(
        trn_type="DEBIT",
        txn_date=date(2026, 8, 18),
        amount=Decimal("-1.99"),
        fitid="202608180",
        name="PAYPAL           PURCHASE   GOOG",
        memo="LE GOOGLE O WEB ID: PAYPALSI77",
        checknum="",
    )


def test_parse_qfx_reads_checknum_when_present(tmp_path):
    qfx_path = tmp_path / "sample.qfx"
    qfx_path.write_text(SAMPLE_QFX)

    record = parse_qfx(qfx_path)[1]

    assert record.checknum == "129"
    assert record.name == "CHECK 129"


def test_parse_qfx_defaults_missing_optional_fields_to_empty_string(tmp_path):
    qfx_path = tmp_path / "sample.qfx"
    qfx_path.write_text(SAMPLE_QFX)

    record = parse_qfx(qfx_path)[2]

    assert record.memo == ""
    assert record.checknum == ""


def test_parse_qfx_skips_malformed_blocks_missing_required_fields(tmp_path):
    qfx_path = tmp_path / "broken.qfx"
    qfx_path.write_text(
        "<STMTTRN>\n<TRNTYPE>DEBIT\n<NAME>Missing date and amount\n</STMTTRN>\n"
    )

    records = parse_qfx(qfx_path)

    assert records == []


def test_parse_qfx_raises_for_missing_file(tmp_path):
    with pytest.raises(OSError):
        parse_qfx(tmp_path / "does-not-exist.qfx")


def test_parse_account_id_extracts_bank_acctid(tmp_path):
    qfx_path = tmp_path / "sample.qfx"
    qfx_path.write_text(SAMPLE_QFX)

    assert parse_account_id(qfx_path) == "597883795"


def test_parse_account_id_extracts_cc_acctid(tmp_path):
    qfx_path = tmp_path / "sample.qfx"
    qfx_path.write_text(
        "<CCSTMTRS>\n<CURDEF>USD\n<CCACCTFROM>\n<ACCTID>1265845169-8964\n</CCACCTFROM>\n"
        "<BANKTRANLIST>\n</BANKTRANLIST>\n</CCSTMTRS>\n"
    )

    assert parse_account_id(qfx_path) == "1265845169-8964"


def test_parse_account_id_returns_none_when_absent(tmp_path):
    qfx_path = tmp_path / "sample.qfx"
    qfx_path.write_text("<STMTTRN>\n<TRNTYPE>DEBIT\n</STMTTRN>\n")

    assert parse_account_id(qfx_path) is None
