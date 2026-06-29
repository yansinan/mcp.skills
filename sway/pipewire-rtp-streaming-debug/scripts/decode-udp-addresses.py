#!/usr/bin/env python3
"""Decode /proc/net/udp and /proc/net/tcp local/remote hex addresses.

/proc/net/{udp,tcp} encodes IPv4 addresses as little-endian 32-bit hex
(bytes reversed) and ports as big-endian 16-bit hex.

Usage:
    decode-udp.py                      # read /proc/net/udp, print all pairs
    decode-udp.py /proc/net/tcp        # read tcp instead
    decode-udp.py 'C0A80166:2693'      # decode a single addr
    grep ':2693' /proc/net/udp | decode-udp.py
"""
import sys
import re

ADDR_RE = re.compile(
    r'^\s*\d+:\s+([0-9A-F]+:[0-9A-F]+)\s+([0-9A-F]+:[0-9A-F]+)\s+'
    r'\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+)'
)


def decode(addr: str) -> str:
    ip_hex, port_hex = addr.split(':')
    ip = '.'.join(str(int(ip_hex[i:i + 2], 16)) for i in (6, 4, 2, 0))
    return f"{ip}:{int(port_hex, 16)}"


def main() -> None:
    if len(sys.argv) == 2 and ':' in sys.argv[1] and sys.argv[1].count(':') == 1:
        # Single address decode
        print(decode(sys.argv[1]))
        return

    path = sys.argv[1] if len(sys.argv) > 1 else '/proc/net/udp'
    with open(path) as f:
        for line in f:
            m = ADDR_RE.match(line)
            if not m:
                continue
            local, remote, inode = m.group(1), m.group(2), m.group(3)
            # state 07 = LISTEN, 01 = ESTABLISHED (UDP "established" just means bound)
            state = line.split()[3]
            print(f"{decode(local):>21} -> {decode(remote):<21} state={state} inode={inode}")


if __name__ == '__main__':
    main()