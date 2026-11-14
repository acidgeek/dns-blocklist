"""Capture iPhone traffic over USB (pcapd) and log which hostnames each process contacts.

Writes one JSON object per observation to the output JSONL file:
  {"t": epoch, "proc": "Facebook", "eproc": "...", "kind": "sni|quic|dns|http|ip", "host": "...", "dst": "ip:port"}

Usage: python capture.py OUT.jsonl [seconds]
"""
import asyncio
import json
import socket
import struct
import sys
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes, hmac

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.pcapd import PcapdService

QUIC_V1_SALT = bytes.fromhex("38762cf7f55934b34d179ae6a4c80cadccbb7f0a")


# ---------------------------------------------------------------- crypto helpers
def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    h = hmac.HMAC(salt, hashes.SHA256())
    h.update(ikm)
    return h.finalize()


def hkdf_expand_label(secret: bytes, label: str, length: int) -> bytes:
    full = b"tls13 " + label.encode()
    info = struct.pack("!H", length) + bytes([len(full)]) + full + b"\x00"
    out, t, i = b"", b"", 1
    while len(out) < length:
        h = hmac.HMAC(secret, hashes.SHA256())
        h.update(t + info + bytes([i]))
        t = h.finalize()
        out += t
        i += 1
    return out[:length]


# ---------------------------------------------------------------- TLS parsing
def sni_from_client_hello(hs: bytes):
    """hs = handshake message bytes starting at handshake type (0x01)."""
    try:
        if not hs or hs[0] != 0x01:
            return None
        p = 4 + 2 + 32  # type+len, version, random
        sid_len = hs[p]
        p += 1 + sid_len
        cs_len = struct.unpack("!H", hs[p:p + 2])[0]
        p += 2 + cs_len
        cm_len = hs[p]
        p += 1 + cm_len
        ext_total = struct.unpack("!H", hs[p:p + 2])[0]
        p += 2
        end = min(len(hs), p + ext_total)
        while p + 4 <= end:
            etype, elen = struct.unpack("!HH", hs[p:p + 4])
            p += 4
            if etype == 0 and p + elen <= len(hs):
                q = p + 2
                while q + 3 <= p + elen:
                    ntype = hs[q]
                    nlen = struct.unpack("!H", hs[q + 1:q + 3])[0]
                    if ntype == 0:
                        return hs[q + 3:q + 3 + nlen].decode("ascii", "replace").lower()
                    q += 3 + nlen
            p += elen
    except Exception:
        return None
    return None


def sni_from_tls_record(payload: bytes):
    if len(payload) < 6 or payload[0] != 0x16 or payload[1] != 0x03:
        return None
    return sni_from_client_hello(payload[5:])


# ---------------------------------------------------------------- QUIC initial
def read_varint(b: bytes, p: int):
    first = b[p]
    ln = 1 << (first >> 6)
    v = first & 0x3F
    for i in range(1, ln):
        v = (v << 8) | b[p + i]
    return v, p + ln


quic_crypto = {}  # dcid -> {offset: bytes}


def quic_initial_sni(pkt: bytes):
    try:
        if len(pkt) < 1200 - 100 or not (pkt[0] & 0x80):
            return None
        if (pkt[0] & 0x30) >> 4 != 0:  # long header type 0 = Initial
            return None
        version = struct.unpack("!I", pkt[1:5])[0]
        if version != 1:
            return None
        p = 5
        dcid_len = pkt[p]
        dcid = pkt[p + 1:p + 1 + dcid_len]
        p += 1 + dcid_len
        scid_len = pkt[p]
        p += 1 + scid_len
        tok_len, p = read_varint(pkt, p)
        p += tok_len
        length, p = read_varint(pkt, p)
        pn_offset = p

        initial_secret = hkdf_extract(QUIC_V1_SALT, dcid)
        cis = hkdf_expand_label(initial_secret, "client in", 32)
        key = hkdf_expand_label(cis, "quic key", 16)
        iv = hkdf_expand_label(cis, "quic iv", 12)
        hp = hkdf_expand_label(cis, "quic hp", 16)

        sample = pkt[pn_offset + 4:pn_offset + 20]
        enc = Cipher(algorithms.AES(hp), modes.ECB()).encryptor()
        mask = enc.update(sample) + enc.finalize()
        first = pkt[0] ^ (mask[0] & 0x0F)
        pn_len = (first & 0x03) + 1
        pn_bytes = bytes(pkt[pn_offset + i] ^ mask[1 + i] for i in range(pn_len))
        pn = int.from_bytes(pn_bytes, "big")
        header = bytes([first]) + pkt[1:pn_offset] + pn_bytes
        payload = pkt[pn_offset + pn_len:pn_offset + length]
        nonce = bytes(a ^ b for a, b in zip(iv, pn.to_bytes(12, "big")))
        plain = AESGCM(key).decrypt(nonce, payload, header)

        frags = quic_crypto.setdefault(dcid, {})
        q = 0
        while q < len(plain):
            ftype = plain[q]
            if ftype == 0x00:  # PADDING
                q += 1
                continue
            if ftype == 0x01:  # PING
                q += 1
                continue
            if ftype == 0x06:  # CRYPTO
                off, q = read_varint(plain, q + 1)
                ln, q = read_varint(plain, q)
                frags[off] = plain[q:q + ln]
                q += ln
                continue
            if ftype in (0x02, 0x03):  # ACK
                _, q = read_varint(plain, q + 1)
                _, q = read_varint(plain, q)
                rc, q = read_varint(plain, q)
                _, q = read_varint(plain, q)
                for _ in range(rc):
                    _, q = read_varint(plain, q)
                    _, q = read_varint(plain, q)
                continue
            break
        # reassemble contiguous data from offset 0
        data, off = b"", 0
        while off in frags:
            data += frags[off]
            off += len(frags[off])
        sni = sni_from_client_hello(data)
        if sni:
            quic_crypto.pop(dcid, None)
        if len(quic_crypto) > 2000:
            quic_crypto.clear()
        return sni
    except Exception:
        return None


# ---------------------------------------------------------------- DNS
def dns_name(b: bytes, p: int, depth=0):
    labels = []
    while True:
        ln = b[p]
        if ln == 0:
            p += 1
            break
        if ln & 0xC0 == 0xC0:
            ptr = struct.unpack("!H", b[p:p + 2])[0] & 0x3FFF
            if depth > 10:
                raise ValueError
            name, _ = dns_name(b, ptr, depth + 1)
            labels.append(name)
            p += 2
            return ".".join(labels), p
        labels.append(b[p + 1:p + 1 + ln].decode("ascii", "replace"))
        p += 1 + ln
    return ".".join(labels), p


def parse_dns(b: bytes):
    """returns (is_response, qname, [answer ips])"""
    flags = struct.unpack("!H", b[2:4])[0]
    qd, an = struct.unpack("!HH", b[4:8])
    p = 12
    qname = None
    for _ in range(qd):
        qname, p = dns_name(b, p)
        p += 4
    ips = []
    if flags & 0x8000:
        for _ in range(an):
            _, p = dns_name(b, p)
            rtype, _, _, rdlen = struct.unpack("!HHIH", b[p:p + 10])
            p += 10
            rd = b[p:p + rdlen]
            if rtype == 1 and rdlen == 4:
                ips.append(socket.inet_ntop(socket.AF_INET, rd))
            elif rtype == 28 and rdlen == 16:
                ips.append(socket.inet_ntop(socket.AF_INET6, rd))
            p += rdlen
    return bool(flags & 0x8000), (qname or "").lower(), ips


# ---------------------------------------------------------------- main loop
ip_to_name = {}
seen_flows = set()


def handle(pkt, out):
    data = bytes(pkt.data)
    if len(data) < 14:
        return
    etype = struct.unpack("!H", data[12:14])[0]
    p = 14
    if etype == 0x0800:
        ihl = (data[p] & 0x0F) * 4
        proto = data[p + 9]
        src = socket.inet_ntop(socket.AF_INET, data[p + 12:p + 16])
        dst = socket.inet_ntop(socket.AF_INET, data[p + 16:p + 20])
        l4 = p + ihl
    elif etype == 0x86DD:
        proto = data[p + 6]
        src = socket.inet_ntop(socket.AF_INET6, data[p + 8:p + 24])
        dst = socket.inet_ntop(socket.AF_INET6, data[p + 24:p + 40])
        l4 = p + 40
    else:
        return
    proc = pkt.comm or ""
    eproc = pkt.ecomm or ""
    rec = None
    if proto == 6 and len(data) >= l4 + 20:
        sport, dport = struct.unpack("!HH", data[l4:l4 + 4])
        off = (data[l4 + 12] >> 4) * 4
        payload = data[l4 + off:]
        if payload:
            sni = sni_from_tls_record(payload)
            if sni:
                rec = {"kind": "sni", "host": sni, "dst": f"{dst}:{dport}"}
            elif dport == 80 and payload[:4] in (b"GET ", b"POST", b"HEAD", b"PUT "):
                for line in payload.split(b"\r\n"):
                    if line.lower().startswith(b"host:"):
                        rec = {"kind": "http", "host": line[5:].strip().decode("ascii", "replace").lower(), "dst": f"{dst}:{dport}"}
                        break
        flags = data[l4 + 13]
        if rec is None and flags & 0x02 and not flags & 0x10:  # SYN
            key = (proc, dst, dport)
            if key not in seen_flows:
                seen_flows.add(key)
                rec = {"kind": "ip", "host": ip_to_name.get(dst, ""), "dst": f"{dst}:{dport}"}
    elif proto == 17 and len(data) >= l4 + 8:
        sport, dport = struct.unpack("!HH", data[l4:l4 + 4])
        payload = data[l4 + 8:]
        if dport == 53 or sport == 53:
            try:
                is_resp, qname, ips = parse_dns(payload)
                if is_resp:
                    for ip in ips:
                        ip_to_name[ip] = qname
                elif qname:
                    rec = {"kind": "dns", "host": qname, "dst": f"{dst}:{dport}"}
            except Exception:
                pass
        elif dport == 443:
            sni = quic_initial_sni(payload)
            if sni:
                rec = {"kind": "quic", "host": sni, "dst": f"{dst}:{dport}"}
    if rec:
        rec.update({"t": round(time.time(), 2), "proc": proc, "eproc": eproc, "if": pkt.interface_name})
        out.write(json.dumps(rec) + "\n")
        out.flush()


async def main(path, seconds):
    lockdown = await create_using_usbmux()
    service = PcapdService(lockdown)
    deadline = time.time() + seconds
    with open(path, "a") as out:
        async for pkt in service.watch():
            try:
                handle(pkt, out)
            except Exception:
                pass
            if time.time() > deadline:
                break


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 600))
