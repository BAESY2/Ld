#!/usr/bin/env python3
"""LS XGT FEnet 실 CPU / pcap 와이어포맷 검증 하니스 (stdlib 전용).

출하 전 **실제 XGK/XGI CPU** 또는 **캡처된 패킷**에 대해 우리 어댑터
(app.comms.fenet_xgt)가 만드는 프레임이 진짜와 바이트 단위로 맞는지 확인하는
정확한 절차를 담는다. 외부 의존 없음(socket/struct/argparse 만).

세 가지 모드:

  1) live   : 환경변수 ``FENET_HOST`` (옵션 ``FENET_PORT``, 기본 2004)로 실 CPU에
              연결, 우리 어댑터로 요청을 보내고 응답을 파싱·해석한다.
              ⚠️ CI 안전: ``FENET_HOST`` 가 없으면 절대 네트워크를 건드리지 않는다.

  2) hex    : ``--hex "4C 53 ..."`` 로 준 기대 바이트열(예: 매뉴얼/Wireshark 16진
              덤프 한 프레임)을 우리 어댑터 산출물과 필드별 대조한다. (오프라인)

  3) pcap   : ``--pcap capture.pcap`` 의 첫 TCP 페이로드(포트 2004)를 추출해
              우리 어댑터 산출물과 필드별 대조한다. libpcap classic 형식만(stdlib).

요청 종류는 ``--op`` 로 선택: ``read-bit`` / ``write-word`` / ``read-word``.
출력은 필드별 PASS/FAIL 표 + 최종 verdict. 종료코드 0=PASS, 1=불일치, 2=사용오류.

예:
    # 오프라인(매뉴얼 예제 한 프레임과 우리 read-bit %MX0 명령블록 대조)
    python scripts/fenet_pcap_verify.py --op read-bit --device %MX0 \\
        --compare-block --hex "54 00 00 00 00 00 01 00 04 00 25 4D 58 30"

    # 실 CPU (CI 에서는 FENET_HOST 미설정 → live 모드 자동 skip)
    FENET_HOST=192.168.0.10 python scripts/fenet_pcap_verify.py --op read-bit --device %MX0
"""

from __future__ import annotations

import argparse
import os
import socket
import struct
import sys

# 어댑터를 패키지로 import 할 수 있도록 리포 루트를 경로에 추가.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.comms.fenet_xgt import (  # noqa: E402
    COMPANY_ID,
    DT_BIT,
    DT_WORD,
    HEADER_LEN,
    SRC_CLIENT,
    build_read_request,
    build_write_request,
    frame,
    parse_header,
)

_DEFAULT_PORT = 2004


# --------------------------------------------------------------------------- #
# 프레임 빌더 (op → (full_adu, command_block))                                  #
# --------------------------------------------------------------------------- #
def build_request(op: str, device: str, value: int, invoke_id: int) -> tuple[bytes, bytes]:
    """선택한 연산의 명령블록과 완성 ADU 를 어댑터로 만든다."""
    if op == "read-bit":
        block = build_read_request(DT_BIT, [device])
    elif op == "read-word":
        block = build_read_request(DT_WORD, [device])
    elif op == "write-word":
        block = build_write_request(DT_WORD, [(device, struct.pack("<H", value & 0xFFFF))])
    else:  # pragma: no cover - argparse choices 가 막음
        raise ValueError(f"unknown op: {op}")
    return frame(block, invoke_id, source=SRC_CLIENT), block


# --------------------------------------------------------------------------- #
# 필드 분해 (LE 전제 — 정형 결론) → 사람이 읽는 (이름, 바이트, 해석) 목록        #
# --------------------------------------------------------------------------- #
def decompose(adu: bytes) -> list[tuple[str, bytes, str]]:
    """ADU 를 헤더+명령블록 필드로 분해한다(전부 little-endian)."""
    rows: list[tuple[str, bytes, str]] = []
    h = adu[:HEADER_LEN]
    rows.append(("Company ID", h[0:10], h[0:8].decode("ascii", "replace")))
    rows.append(("PLC Info", h[10:12], "reserved"))
    rows.append(("CPU Info", h[12:13], f"0x{h[12]:02X}"))
    rows.append(("Source", h[13:14], f"0x{h[13]:02X}"))
    rows.append(("Invoke ID(LE)", h[14:16], str(struct.unpack("<H", h[14:16])[0])))
    rows.append(("Length(LE)", h[16:18], str(struct.unpack("<H", h[16:18])[0])))
    rows.append(("FEnet Pos", h[18:19], f"0x{h[18]:02X}"))
    rows.append(("BCC", h[19:20], f"0x{h[19]:02X}"))

    b = adu[HEADER_LEN:]
    if len(b) >= 8:
        cmd, dtype, _rsv, blk = struct.unpack("<HHHH", b[:8])
        rows.append(("Command(LE)", b[0:2], f"0x{cmd:04X}"))
        rows.append(("Data Type(LE)", b[2:4], f"0x{dtype:04X}"))
        rows.append(("Reserved", b[4:6], "0x0000"))
        rows.append(("Block Count(LE)", b[6:8], str(blk)))
        off = 8
        if len(b) >= off + 2:
            (nlen,) = struct.unpack("<H", b[off : off + 2])
            rows.append(("Var-name Len(LE)", b[off : off + 2], str(nlen)))
            off += 2
            name = b[off : off + nlen]
            rows.append(("Var Name", name, name.decode("ascii", "replace")))
            off += nlen
            if off < len(b):  # 쓰기: 데이터 카운트 + 데이터
                if len(b) >= off + 2:
                    (dcnt,) = struct.unpack("<H", b[off : off + 2])
                    rows.append(("Data Cnt(LE)", b[off : off + 2], str(dcnt)))
                    off += 2
                    rows.append(("Data(LE)", b[off : off + dcnt], b[off : off + dcnt].hex()))
    return rows


def _hexstr(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


# --------------------------------------------------------------------------- #
# 대조 표 출력                                                                  #
# --------------------------------------------------------------------------- #
def compare_table(ours: bytes, theirs: bytes, *, scope: str) -> bool:
    """우리 바이트 vs 기준 바이트를 필드별로 표 출력하고 전체 PASS 여부 반환.

    scope: "block"(명령블록만) 또는 "adu"(헤더 BCC/Invoke 제외하고 비교 시 주의).
    필드 분해는 ADU 기준이므로, block 비교 시에는 더미 헤더를 붙여 정렬한다.
    """
    if scope == "block":
        dummy = b"\x00" * HEADER_LEN
        ours_rows = decompose(dummy + ours)[8:]  # 헤더 8행 건너뜀
        theirs_rows = decompose(dummy + theirs)[8:]
    else:
        ours_rows = decompose(ours)
        theirs_rows = decompose(theirs)

    print(f"{'FIELD':<18}{'OURS':<26}{'REFERENCE':<26}{'OK'}")
    print("-" * 76)
    all_ok = True
    n = max(len(ours_rows), len(theirs_rows))
    for i in range(n):
        oname, obytes, oval = ours_rows[i] if i < len(ours_rows) else ("(missing)", b"", "")
        tname, tbytes, _tval = theirs_rows[i] if i < len(theirs_rows) else ("(missing)", b"", "")
        ok = obytes == tbytes and oname == tname
        all_ok = all_ok and ok
        name = oname if oname != "(missing)" else tname
        print(
            f"{name:<18}{_hexstr(obytes)+' ('+oval+')':<26}"
            f"{_hexstr(tbytes):<26}{'PASS' if ok else 'FAIL'}"
        )
    print("-" * 76)
    print(f"VERDICT: {'PASS — wire format matches reference' if all_ok else 'FAIL — mismatch'}")
    return all_ok


# --------------------------------------------------------------------------- #
# pcap (libpcap classic) 첫 페이로드 추출 — stdlib 만                            #
# --------------------------------------------------------------------------- #
def first_fenet_payload_from_pcap(path: str, port: int) -> bytes:
    """classic .pcap 에서 TCP 포트 ``port`` 의 첫 비어있지 않은 페이로드를 뽑는다.

    Ethernet II + IPv4 + TCP 만 가정(가장 흔한 캡처). 다른 링크계층/IPv6 는 미지원.
    """
    with open(path, "rb") as fp:
        data = fp.read()
    if len(data) < 24:
        raise ValueError("pcap too short")
    magic = data[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"):
        endian = "<" if magic == b"\xd4\xc3\xb2\xa1" else ">"
    else:
        raise ValueError("not a classic .pcap (use tcpdump -w, not pcapng)")
    off = 24  # global header
    while off + 16 <= len(data):
        _ts, _us, caplen, _orig = struct.unpack(endian + "IIII", data[off : off + 16])
        off += 16
        pkt = data[off : off + caplen]
        off += caplen
        payload = _tcp_payload(pkt, port)
        if payload:
            return payload
    raise ValueError(f"no TCP payload on port {port} found in pcap")


def _tcp_payload(pkt: bytes, port: int) -> bytes:
    """Ethernet II/IPv4/TCP 프레임에서 지정 포트가 관여한 TCP 페이로드를 돌려준다."""
    if len(pkt) < 14 or pkt[12:14] != b"\x08\x00":  # EtherType IPv4
        return b""
    ip = pkt[14:]
    if len(ip) < 20 or (ip[0] >> 4) != 4:
        return b""
    ihl = (ip[0] & 0x0F) * 4
    if ip[9] != 6:  # protocol TCP
        return b""
    total = struct.unpack(">H", ip[2:4])[0]
    tcp = ip[ihl:total]
    if len(tcp) < 20:
        return b""
    sport, dport = struct.unpack(">HH", tcp[0:4])
    if port not in (sport, dport):
        return b""
    data_off = (tcp[12] >> 4) * 4
    return tcp[data_off:]


# --------------------------------------------------------------------------- #
# live 모드 (env-guarded)                                                       #
# --------------------------------------------------------------------------- #
def run_live(op: str, device: str, value: int, host: str, port: int) -> int:
    """실 CPU 에 어댑터로 요청을 보내고 응답을 해석·출력한다(env-guarded)."""
    print(f"[live] connecting to real LS CPU {host}:{port} ...")
    invoke = 0x0001
    adu, _block = build_request(op, device, value, invoke)
    print("[live] sending ADU:")
    print("       " + _hexstr(adu))
    sock = socket.create_connection((host, port), timeout=5.0)
    sock.settimeout(5.0)
    try:
        sock.sendall(adu)
        head = _recv_exact(sock, HEADER_LEN)
        src, r_invoke, length = parse_header(head)
        body = _recv_exact(sock, length)
    finally:
        sock.close()
    print("[live] response header decoded:")
    for name, raw, val in decompose(head + body):
        print(f"       {name:<18}{_hexstr(raw):<24}{val}")
    if head[:8] != COMPANY_ID:
        print("VERDICT: FAIL — bad company id in response")
        return 1
    if r_invoke != invoke:
        print(f"VERDICT: FAIL — invoke mismatch sent={invoke} got={r_invoke}")
        return 1
    cmd, _dt, _rsv, errstate = struct.unpack("<HHHH", body[:8])
    if errstate != 0:
        print(f"VERDICT: FAIL — PLC NAK error state 0x{errstate:04X} (cmd 0x{cmd:04X})")
        return 1
    print(f"VERDICT: PASS — real CPU accepted our frame (src=0x{src:02X}, len={length})")
    return 0


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise OSError("connection closed by peer")
        buf.extend(chunk)
    return bytes(buf)


# --------------------------------------------------------------------------- #
# main                                                                          #
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--op", choices=["read-bit", "read-word", "write-word"], default="read-bit")
    parser.add_argument("--device", default="%MX0", help='LS device name (e.g. "%%MX0")')
    parser.add_argument("--value", type=lambda s: int(s, 0), default=1, help="write-word value")
    parser.add_argument("--invoke", type=lambda s: int(s, 0), default=1, help="비교용 Invoke ID")
    parser.add_argument("--hex", dest="hexref", help="기준 바이트열(16진, 공백 허용)")
    parser.add_argument("--pcap", help="classic .pcap 경로(첫 2004 포트 페이로드 사용)")
    parser.add_argument(
        "--compare-block",
        action="store_true",
        help="명령블록만 비교(헤더 BCC/Invoke 제외). 미지정 시 전체 ADU 비교.",
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("FENET_PORT", _DEFAULT_PORT))
    )
    args = parser.parse_args(argv)

    host = os.environ.get("FENET_HOST")

    # --- 오프라인 대조 모드 (hex / pcap) -------------------------------------- #
    if args.hexref or args.pcap:
        adu, block = build_request(args.op, args.device, args.value, args.invoke)
        if args.pcap:
            try:
                ref = first_fenet_payload_from_pcap(args.pcap, args.port)
            except (OSError, ValueError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
        else:
            ref = bytes.fromhex(args.hexref.replace(" ", "").replace("0x", ""))
        if args.compare_block:
            ok = compare_table(block, ref, scope="block")
        else:
            ok = compare_table(adu, ref, scope="adu")
        return 0 if ok else 1

    # --- live 모드 (env-guarded; CI 안전) ------------------------------------ #
    if host:
        return run_live(args.op, args.device, args.value, host, args.port)

    print(
        "no FENET_HOST set and no --hex/--pcap given: nothing to do.\n"
        "  * offline:  --hex \"54 00 ...\"  또는  --pcap capture.pcap\n"
        "  * real CPU: FENET_HOST=<ip> python scripts/fenet_pcap_verify.py --op read-bit\n"
        "이 스크립트는 FENET_HOST 가 없으면 네트워크를 건드리지 않는다(CI 안전).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
