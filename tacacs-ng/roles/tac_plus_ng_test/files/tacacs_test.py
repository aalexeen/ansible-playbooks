#!/usr/bin/env python3
"""
tacacs_test.py — minimal TACACS+ authentication test.
Sends an Authentication START packet and checks for a valid response.
Does NOT require any external libraries (stdlib only).

Usage:
  python3 tacacs_test.py --host 127.0.0.1 --port 49 \
      --key 'mysecret' --user htc-ro [--password 'pass']

Exit codes:
  0 — received a valid TACACS+ response (PASS or FAIL — server is alive)
  1 — connection refused / timeout / invalid response
"""

import argparse
import hashlib
import hmac
import socket
import struct
import sys

# TACACS+ packet types
TAC_PLUS_AUTHEN = 0x01
TAC_PLUS_AUTHOR = 0x02
TAC_PLUS_ACCT   = 0x03

# TACACS+ header flags
TAC_PLUS_UNENCRYPTED_FLAG = 0x04
TAC_PLUS_SINGLE_CONNECT_FLAG = 0x08

# Authen START action / type / service
TAC_PLUS_AUTHEN_LOGIN  = 0x01
TAC_PLUS_AUTHEN_TYPE_ASCII = 0x01
TAC_PLUS_AUTHEN_SVC_LOGIN  = 0x01

# Authen REPLY status
TAC_PLUS_AUTHEN_STATUS_PASS    = 0x01
TAC_PLUS_AUTHEN_STATUS_FAIL    = 0x02
TAC_PLUS_AUTHEN_STATUS_GETDATA = 0x03
TAC_PLUS_AUTHEN_STATUS_GETUSER = 0x04
TAC_PLUS_AUTHEN_STATUS_GETPASS = 0x05
TAC_PLUS_AUTHEN_STATUS_RESTART = 0x06
TAC_PLUS_AUTHEN_STATUS_ERROR   = 0x07

HEADER_LEN = 12


def pseudo_pad(key: bytes, session_id: int, seq_no: int, version: int, body_len: int) -> bytes:
    """Generate TACACS+ obfuscation pad.

    Per tac_plus-ng source (packet.c md5_xor):
      MD5(session_id + key + version + seq_no [+ prev_hash])
    Note: session_id is first, then key — opposite of some third-party docs.
    """
    sid_bytes = session_id.to_bytes(4, "big")
    pad = b""
    prev = b""
    for i in range(0, body_len, 16):
        if i == 0:
            prev = hashlib.md5(sid_bytes + key + bytes([version]) + bytes([seq_no])).digest()
        else:
            prev = hashlib.md5(sid_bytes + key + bytes([version]) + bytes([seq_no]) + prev).digest()
        pad += prev
    return pad[:body_len]


def xor_body(body: bytes, pad: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(body, pad))


def build_authen_continue(password: str, session_id: int, key: bytes, version: int, seq_no: int) -> bytes:
    """Build a TACACS+ Authentication CONTINUE packet (seq_no must be odd: 3, 5, ...)."""
    # Body: user_msg_len(2), data_len(2), flags(1), user_msg, data
    pass_b = password.encode()
    body = struct.pack("!HHB", len(pass_b), 0, 0) + pass_b
    pad = pseudo_pad(key, session_id, seq_no, version, len(body))
    obfuscated = xor_body(body, pad)
    header = struct.pack("!BBBBII", version, TAC_PLUS_AUTHEN, seq_no, 0, session_id, len(body))
    return header + obfuscated


def build_authen_start(user: str, password: str, session_id: int, key: bytes) -> bytes:
    """Build a TACACS+ Authentication START packet."""
    version = 0xC0  # TAC_PLUS_VER_DEFAULT (major=0xC, minor=0)
    # Note: 0xc1 (VER_ONE) is also accepted for authen, but 0xc0 is safer default

    user_b = user.encode()
    port_b = b"tty0"
    rem_addr_b = b"ansible-test"
    data_b = password.encode() if password else b""

    # Body per RFC 8907 Section 5.1:
    #   action(1), priv_lvl(1), authen_type(1), authen_service(1),
    #   user_len(1), port_len(1), rem_addr_len(1), data_len(1),
    #   user, port, rem_addr, data
    body = struct.pack(
        "!BBBBBBBB",
        TAC_PLUS_AUTHEN_LOGIN,      # action
        0x00,                        # priv_lvl = 0
        TAC_PLUS_AUTHEN_TYPE_ASCII,  # authen_type
        TAC_PLUS_AUTHEN_SVC_LOGIN,   # authen_service
        len(user_b),                 # user_len
        len(port_b),                 # port_len
        len(rem_addr_b),             # rem_addr_len
        len(data_b),                 # data_len
    )
    body += user_b + port_b + rem_addr_b + data_b

    seq_no = 1
    pad = pseudo_pad(key, session_id, seq_no, version, len(body))
    obfuscated = xor_body(body, pad)

    header = struct.pack(
        "!BBBBII",
        version,
        TAC_PLUS_AUTHEN,
        seq_no,
        0,            # flags (encrypted)
        session_id,
        len(body),
    )
    return header + obfuscated


def parse_reply(data: bytes, session_id: int, key: bytes, debug: bool = False) -> dict:
    """Parse TACACS+ header + authen reply body."""
    if len(data) < HEADER_LEN:
        raise ValueError(f"Response too short: {len(data)} bytes")

    version, pkt_type, seq_no, flags, sid, length = struct.unpack("!BBBBII", data[:HEADER_LEN])

    if debug:
        print(f"  [debug] header: version=0x{version:02x} type=0x{pkt_type:02x} seq={seq_no} "
              f"flags=0x{flags:02x} session_id=0x{sid:08x} length={length}", file=sys.stderr)
        print(f"  [debug] raw response ({len(data)} bytes): {data.hex()}", file=sys.stderr)

    if sid != session_id:
        raise ValueError(f"Session ID mismatch: got 0x{sid:08x}, expected 0x{session_id:08x}")

    body_enc = data[HEADER_LEN:HEADER_LEN + length]

    # TAC_PLUS_UNENCRYPTED_FLAG (0x04) — body is plaintext, no XOR needed
    if flags & 0x04:
        body = body_enc
        if debug:
            print(f"  [debug] body (unencrypted): {body.hex()}", file=sys.stderr)
    else:
        pad = pseudo_pad(key, sid, seq_no, version, length)
        body = xor_body(body_enc, pad)
        if debug:
            print(f"  [debug] body_enc: {body_enc.hex()}", file=sys.stderr)
            print(f"  [debug] pad:      {pad.hex()}", file=sys.stderr)
            print(f"  [debug] body dec: {body.hex()}", file=sys.stderr)

    if len(body) < 6:
        raise ValueError("Reply body too short")

    status, flags_body, srv_msg_len, data_len = struct.unpack("!BBHH", body[:6])
    srv_msg = body[6:6 + srv_msg_len].decode(errors="replace") if srv_msg_len else ""
    data_field = body[6 + srv_msg_len:6 + srv_msg_len + data_len].decode(errors="replace") if data_len else ""

    if debug and (srv_msg or data_field):
        print(f"  [debug] server_msg={srv_msg!r} data={data_field!r}", file=sys.stderr)

    return {"status": status, "seq_no": seq_no, "server_msg": srv_msg}


STATUS_NAMES = {
    TAC_PLUS_AUTHEN_STATUS_PASS:    "PASS",
    TAC_PLUS_AUTHEN_STATUS_FAIL:    "FAIL",
    TAC_PLUS_AUTHEN_STATUS_GETDATA: "GETDATA",
    TAC_PLUS_AUTHEN_STATUS_GETUSER: "GETUSER",
    TAC_PLUS_AUTHEN_STATUS_GETPASS: "GETPASS",
    TAC_PLUS_AUTHEN_STATUS_RESTART: "RESTART",
    TAC_PLUS_AUTHEN_STATUS_ERROR:   "ERROR",
}


def main():
    parser = argparse.ArgumentParser(description="Minimal TACACS+ auth test")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=49)
    parser.add_argument("--key", required=True, help="TACACS+ shared key")
    parser.add_argument("--user", required=True, help="Username to test")
    parser.add_argument("--password", default="", help="Password (optional; omit for GETPASS response)")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--debug", action="store_true", help="Print raw packet debug info")
    args = parser.parse_args()

    key = args.key.encode()
    if args.debug:
        print(f"  [debug] key as received by Python: {key!r} (len={len(key)})", file=sys.stderr)
    session_id = 0xDEADBEEF  # fixed for simplicity

    pkt = build_authen_start(args.user, args.password, session_id, key)

    version = 0xC0  # must match build_authen_start

    try:
        with socket.create_connection((args.host, args.port), timeout=args.timeout) as s:
            s.sendall(pkt)
            response = s.recv(4096)

            try:
                reply = parse_reply(response, session_id, key, debug=args.debug)
            except ValueError as e:
                print(f"ERROR parsing response: {e}", file=sys.stderr)
                sys.exit(1)

            # If server asks for password via continue exchange, send it
            if reply["status"] == TAC_PLUS_AUTHEN_STATUS_GETPASS and args.password:
                cont_pkt = build_authen_continue(args.password, session_id, key, version, seq_no=3)
                s.sendall(cont_pkt)
                response2 = s.recv(4096)
                try:
                    reply = parse_reply(response2, session_id, key, debug=args.debug)
                except ValueError as e:
                    print(f"ERROR parsing continue response: {e}", file=sys.stderr)
                    sys.exit(1)

    except ConnectionRefusedError:
        print(f"ERROR: Connection refused to {args.host}:{args.port}", file=sys.stderr)
        sys.exit(1)
    except socket.timeout:
        print(f"ERROR: Timeout connecting to {args.host}:{args.port}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    status_name = STATUS_NAMES.get(reply["status"], f"UNKNOWN(0x{reply['status']:02x})")
    srv_msg = reply.get("server_msg", "")
    print(f"TACACS+ response from {args.host}:{args.port} — status={status_name}"
          + (f" ({srv_msg})" if srv_msg else ""))

    if reply["status"] == TAC_PLUS_AUTHEN_STATUS_PASS:
        print("OK: authentication PASSED")
        sys.exit(0)
    elif reply["status"] == TAC_PLUS_AUTHEN_STATUS_FAIL:
        print("OK: server is alive (authentication FAILED — check credentials)")
        sys.exit(0)
    elif reply["status"] in (
        TAC_PLUS_AUTHEN_STATUS_GETPASS,
        TAC_PLUS_AUTHEN_STATUS_GETUSER,
        TAC_PLUS_AUTHEN_STATUS_GETDATA,
    ):
        # Still in dialog — server is alive
        print("OK: server is alive and responding to TACACS+ packets")
        sys.exit(0)
    else:
        print(f"WARN: unexpected status {status_name}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
