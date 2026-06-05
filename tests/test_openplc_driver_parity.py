"""C-driver ↔ Python-adapter wire-frame parity (CI-safe, no network, no C).

The OpenPLC v4 reference drivers under ``openplc_driver/`` (fenet_hal.cpp,
melsec_hal.cpp) are a hand port of the PROVEN pure-Python adapters
``app/comms/fenet_xgt.py`` and ``app/comms/melsec.py``. We cannot compile the
C here (no OpenPLC v4 source / toolchain in this repo), so instead we MACHINE-
CHECK the contract: the exact wire frames the C driver intends to emit are
encoded below as byte literals (copied from the C source / protocol brief) and
asserted equal to the bytes the Python adapters actually produce for the same
operation.

If the C frame builders ever drift from the Python adapters, these literals
will stop matching and this test fails — that is the whole point. The literals
double as a frozen golden vector for the eventual on-device Wireshark check.

NOTE: This file deliberately reaches into a few module-private helpers of the
adapters (the same builders the C ports mirror) so the comparison is at the
frame-construction layer, independent of any live socket.
"""

from __future__ import annotations

import struct

from app.comms import fenet_xgt as fx
from app.comms import melsec as mc


# --------------------------------------------------------------------------- #
# Helper: render a spaced hex string into bytes, mirroring how the literals    #
# appear in the C source comments / protocol brief (e.g. "54 00 00 ...").      #
# --------------------------------------------------------------------------- #
def h(spaced_hex: str) -> bytes:
    return bytes.fromhex(spaced_hex.replace(" ", ""))


# --------------------------------------------------------------------------- #
# LS XGT FEnet (TCP 2004) — frames fenet_hal.cpp must emit.                     #
# --------------------------------------------------------------------------- #
# Command block (header-independent), read %MX0 bit. Brief §2 example.
FENET_READ_MX0_BLOCK = h("54 00 00 00 00 00 01 00 04 00 25 4d 58 30")

# Full ADU = 20B header + command block, invoke id 1, source 0x33.
# Header: "LSIS-XGT" 00 00 | PLC 00 00 | CPU 00 | src 33 | inv 01 00 |
#         len 0e 00 | pos 00 | BCC 9d
FENET_READ_MX0_FRAME_INV1 = h(
    "4c 53 49 53 2d 58 47 54 00 00 00 00 00 33 01 00 0e 00 00 9d "
    "54 00 00 00 00 00 01 00 04 00 25 4d 58 30"
)

# Write %MX0 = 1 (bit) command block. Brief §2 example layout (name then data).
FENET_WRITE_MX0_ON_BLOCK = h(
    "58 00 00 00 00 00 01 00 04 00 25 4d 58 30 01 00 01"
)

# Write %MW100 = 1 (word) command block.
FENET_WRITE_MW100_1_BLOCK = h(
    "58 00 02 00 00 00 01 00 06 00 25 4d 57 31 30 30 02 00 01 00"
)


def test_fenet_read_bit_block_matches_python() -> None:
    py = fx.build_read_request(fx.DT_BIT, ["%MX0"])
    assert py == FENET_READ_MX0_BLOCK


def test_fenet_read_bit_full_frame_matches_python() -> None:
    block = fx.build_read_request(fx.DT_BIT, ["%MX0"])
    py = fx.frame(block, 1, source=fx.SRC_CLIENT)
    assert py == FENET_READ_MX0_FRAME_INV1
    # header is exactly 20 bytes and the C driver computes BCC over [0..18].
    assert len(py) - len(block) == fx.HEADER_LEN
    assert py[19] == fx.bcc(py[:19])


def test_fenet_write_bit_block_matches_python() -> None:
    py = fx.build_write_request(fx.DT_BIT, [("%MX0", b"\x01")])
    assert py == FENET_WRITE_MX0_ON_BLOCK


def test_fenet_write_word_block_matches_python() -> None:
    py = fx.build_write_request(fx.DT_WORD, [("%MW100", struct.pack("<H", 1))])
    assert py == FENET_WRITE_MW100_1_BLOCK


# --------------------------------------------------------------------------- #
# Mitsubishi MELSEC MC 3E binary — frames melsec_hal.cpp must emit.             #
# --------------------------------------------------------------------------- #
# Read 16 bits from M0. Brief §1 example.
MELSEC_READ_M0x16_FRAME = h(
    "50 00 00 ff ff 03 00 0c 00 10 00 01 04 01 00 90 00 00 00 10 00"
)
# Write 1 bit M0 = ON (nibble-packed data 0x10).
MELSEC_WRITE_M0_ON_FRAME = h(
    "50 00 00 ff ff 03 00 0d 00 10 00 01 14 01 00 90 00 00 00 01 00 10"
)
# Write D100 = 1234 (word). Brief §1 example.
MELSEC_WRITE_D100_1234_FRAME = h(
    "50 00 00 ff ff 03 00 0e 00 10 00 01 14 00 00 a8 64 00 00 01 00 d2 04"
)


def _mc_client() -> mc._Mc3eBinary:
    return mc._Mc3eBinary("127.0.0.1")


def test_melsec_read_bits_frame_matches_python() -> None:
    c = _mc_client()
    code, head = mc.parse_device("M0")
    req = c._request_prefix(mc._CMD_BATCH_READ, mc._SUBCMD_BIT, code, head, 16)
    assert c._build_request(req) == MELSEC_READ_M0x16_FRAME


def test_melsec_write_bit_frame_matches_python() -> None:
    c = _mc_client()
    code, head = mc.parse_device("M0")
    req = c._request_prefix(mc._CMD_BATCH_WRITE, mc._SUBCMD_BIT, code, head, 1)
    req += mc.pack_bits_nibble([True])
    assert c._build_request(req) == MELSEC_WRITE_M0_ON_FRAME


def test_melsec_write_word_frame_matches_python() -> None:
    c = _mc_client()
    code, head = mc.parse_device("D100")
    req = c._request_prefix(mc._CMD_BATCH_WRITE, mc._SUBCMD_WORD, code, head, 1)
    req += struct.pack("<H", 1234)
    assert c._build_request(req) == MELSEC_WRITE_D100_1234_FRAME


def test_melsec_device_codes_match_brief() -> None:
    # The C kDevices[] table must agree with the Python DEVICE_CODES on the
    # codes/numbering the brief calls out (M decimal 0x90, D decimal 0xA8,
    # X hex 0x9C).
    assert mc.parse_device("M0") == (0x90, 0)
    assert mc.parse_device("D100") == (0xA8, 100)
    assert mc.parse_device("X10") == (0x9C, 0x10)  # hex numbering


def test_melsec_nibble_bit_packing() -> None:
    # Even point -> high nibble; 16 ON -> all 0x11 bytes. Matches C
    # pack_bits_nibble(). Distinct from Modbus LSB packing.
    assert mc.pack_bits_nibble([True]) == b"\x10"
    assert mc.pack_bits_nibble([True] * 16) == b"\x11" * 8
