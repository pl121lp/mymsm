"""Parser for QFX/OFX bank-statement files (SGML-style, unclosed leaf tags)."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

_STMTTRN_RE = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<([A-Za-z0-9.]+)>(.*)")
_ACCTID_RE = re.compile(r"<ACCTID>(.+)", re.IGNORECASE)


@dataclass(frozen=True)
class QfxRecord:
    trn_type: str
    txn_date: date
    amount: Decimal
    fitid: str
    name: str
    memo: str
    checknum: str


def _parse_ofx_date(raw):
    return date(int(raw[0:4]), int(raw[4:6]), int(raw[6:8]))


def _parse_block(block_text):
    fields = {}
    for line in block_text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _TAG_RE.match(line)
        if not match:
            continue
        fields[match.group(1).upper()] = match.group(2).strip()

    dtposted = fields.get("DTPOSTED")
    trnamt = fields.get("TRNAMT")
    if not dtposted or not trnamt:
        return None
    try:
        amount = Decimal(trnamt)
        txn_date = _parse_ofx_date(dtposted)
    except (InvalidOperation, ValueError):
        return None

    return QfxRecord(
        trn_type=fields.get("TRNTYPE", ""),
        txn_date=txn_date,
        amount=amount,
        fitid=fields.get("FITID", ""),
        name=fields.get("NAME", ""),
        memo=fields.get("MEMO", ""),
        checknum=fields.get("CHECKNUM", ""),
    )


def parse_qfx(path):
    """Reads a QFX/OFX file and returns the STMTTRN records it contains as
    a list of QfxRecord. Blocks missing a postable date or amount are
    skipped rather than raising, since a malformed record shouldn't block
    importing the rest of the file."""
    with open(path, "r", encoding="cp1252", errors="replace") as qfx_file:
        text = qfx_file.read()

    records = []
    for block_text in _STMTTRN_RE.findall(text):
        record = _parse_block(block_text)
        if record is not None:
            records.append(record)
    return records


def parse_account_id(path):
    """Reads a QFX/OFX file and returns the ACCTID from its account-header
    block (BANKACCTFROM or CCACCTFROM), or None if the file has none."""
    with open(path, "r", encoding="cp1252", errors="replace") as qfx_file:
        text = qfx_file.read()

    match = _ACCTID_RE.search(text)
    return match.group(1).strip() if match else None
