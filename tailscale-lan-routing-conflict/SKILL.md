---
name: tailscale-lan-routing-conflict
description: |
  Diagnose and fix the symptom "Tailscale IP (100.x.x.x) ping 通 / LAN IP (192.168.x.x) ping 不通" on Tailscale nodes that share a LAN segment. Root cause is Tailscale's route table 52 hijacking the local LAN subnet, forcing ICMP replies through the tailscale0 TUN — Tailscale rewrites the reply's src IP to the Tailscale IP, so the peer's `ping <lan-ip>` sees a src mismatch and drops the reply.
---

# Symptom

- `ping <tailscale-ip>` works (e.g. `100.66.66.249` ↔ `100.66.66.102`).
- `ping <lan-ip>` from a peer on the same physical LAN gets **0 received, 100% packet loss**, even though both nodes have REACHABLE ARP entries for each other.
- This is **NOT** a firewall issue, **NOT** an AP isolation issue (ARP works both ways), **NOT** an ICMP rate-limit issue.

# Root Cause

When Tailscale detects peers on the same LAN segment, it installs routes in **policy routing table 52** so that traffic to peer LAN IPs is forced through `tailscale0` (the TUN). The Tailscale daemon then performs "LAN direct optimization" by **rewriting the source IP** of outgoing packets to the local Tailscale IP (e.g. `100.66.66.249`).

This breaks ICMP echo symmetry when the reply is triggered by a peer's raw `ping <lan-ip>`:

| Step | Path |
|---|---|
| 1. helix `ping 192.168.1.249` | helix sends ICMP echo req via raw LAN |
| 2. x1tablet receives on `wlp4s0` | TCPdump sees echo request, normal |
| 3. x1tablet generates echo reply | src=192.168.1.249, dst=192.168.1.102 |
| 4. FIB lookup for dst=192.168.1.102 | matches table 52 → `dev tailscale0` |
| 5. tailscale0 → Tailscale daemon | **rewrites reply src to 100.66.66.249** |
| 6. helix receives reply | src=100.66.66.249, but helix's ping socket expects src=192.168.1.249 |
| 7. helix kernel drops the reply | ping reports 0 received |

Note: `x1tablet → helix` ping also goes through tailscale0 and has src rewritten — but **both sides are in Tailscale**, so the Tailscale daemon at the receiving end restores the original LAN src before delivering to the raw socket. This is why active ping from the affected node works but inbound ping to its LAN IP doesn't.

# Diagnostic Checklist

Run on the node that can't be reached on its LAN IP:

```bash
# 1. Confirm the symptom (peer's perspective)
ssh dr@<peer> "ping -c3 -W2 <lan-ip-of-this-node>"
# → expect: 100% packet loss, 0 received

# 2. Confirm Tailscale IP works
ssh dr@<peer> "ping -c3 -W2 <tailscale-ip-of-this-node>"
# → expect: 3 received

# 3. Identify the route hijack
ip route get <peer-lan-ip>
# BAD:  <peer-lan-ip> dev tailscale0 table 52 src <tailscale-ip>
# GOOD: <peer-lan-ip> dev <physical-iface> src <lan-ip>

# 4. Inspect table 52 for local-subnet routes
ip route show table 52 | grep <lan-subnet>
# BAD:  192.168.1.0/24 dev tailscale0
# GOOD: (empty — no entry for the local subnet)

# 5. Confirm with tcpdump on tailscale0 while you actively ping the peer
sudo tcpdump -i tailscale0 -n -p 'icmp' &
ping -c 3 <peer-lan-ip>
# BAD:  src shows <tailscale-ip> instead of <lan-ip>
```

# Fix

```bash
sudo tailscale set --accept-routes=false
```

This tells the local Tailscale daemon not to install routes for peer-reachable subnets in table 52. Verify:

```bash
ip route get <peer-lan-ip>     # should now show <physical-iface>, not tailscale0
ip route show table 52 | grep <lan-subnet>   # should be empty
ssh dr@<peer> "ping -c3 -W2 <this-node-lan-ip>"   # should now show 3/3 received
```

The change is persisted in `/var/lib/tailscale/tailscaled.state` and survives reboot. No systemd unit or startup flag change needed — `tailscale set` writes directly to the daemon's state file.

# Why This Works

`accept-routes=false` controls not only "accept subnet routes from other nodes" but also the local table-52 routes that Tailscale installs by default for any subnet it discovers on peers' interfaces. Disabling it lets the kernel's normal `main` table handle the local subnet, so echo replies go out via `wlp4s0` with src=192.168.1.249 intact, matching what the peer's `ping` socket expects.

# Don't Confuse With

| Misdiagnosis | Why It's Wrong |
|---|---|
| "Local firewall drops ICMP" | `iptables -L INPUT -v` shows policy ACCEPT, no DROP rule. ARP+ICMP request both arrive on wlp4s0 — only the reply is missing. |
| "AP isolation between WiFi segments" | ARP table shows REACHABLE entries for the peer, ICMP echo requests arrive on wlp4s0. AP isolation would block ARP itself. |
| "Kernel ICMP rate limit" | `/proc/net/snmp` shows `OutEchoReps ≈ InEchos` (almost every request has a reply sent). `icmp_ratemask` default 6168 = bit 3+4+11+12, **does not include echo reply (bit 0)**. |
| "rp_filter strict mode drops asymmetric reply" | wlp4s0 rp_filter is 2 but the reply's src/dst matches the FIB return path on wlp4s0 — passes. |

# Verification Snippet (full evidence chain)

```bash
# On the affected node
sudo tcpdump -i wlp4s0 -n -p 'icmp' &
sleep 2
ssh dr@<peer> "ping -c 5 -i 1 <lan-ip>"
# → expect echo requests visible on wlp4s0, 0 echo replies

sudo tcpdump -i tailscale0 -n -p 'icmp' &
sleep 2
# active ping from this node
ping -c 5 -i 1 <peer-lan-ip>
# → expect ICMP packets on tailscale0 with src = <tailscale-ip>, not <lan-ip>

# After fix:
sudo tailscale set --accept-routes=false
ssh dr@<peer> "ping -c 3 <lan-ip>"   # should now succeed
```

# Context

Discovered on x1tablet (192.168.1.249 / 100.66.66.249) ↔ helix (192.168.1.102 / 100.66.66.102) on 2026-06-28. helix & serverhome reported 1292 / 1228 packets 100% loss over 22 minutes of continuous ping; x1tablet's wlp4s0 tcpdump confirmed echo requests arrived but no echo replies were emitted on wlp4s0. tailscale0 tcpdump showed the reply going out with src rewritten to 100.66.66.249, which helix's ping socket (bound to dst=192.168.1.249) rejected as src mismatch. `sudo tailscale set --accept-routes=false` cleared the table 52 hijack and ping 192.168.1.249 returned to 5-6 ms RTT (LAN direct, no Tailscale tunnel).