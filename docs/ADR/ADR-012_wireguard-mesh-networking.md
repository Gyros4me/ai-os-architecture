# ADR-012: Mesh Networking with WireGuard

**Status:** Accepted  
**Date:** 2026-02-17  
**Authors:** Alessandro La Gamba  
**Deciders:** Architecture team  

---

## Context

Inter-OS communication in the constellation (ADR-030) crosses trust boundaries: two 0xMeridian nodes may be owned by different organizations, located in different networks, with no shared PKI infrastructure. The communication substrate must provide:

1. **Mutual authentication** without a central Certificate Authority
2. **Perfect Forward Secrecy** — compromise of a long-term key doesn't expose past traffic
3. **Low overhead** — Bus 4 (<50ms) must not be dominated by cryptographic overhead
4. **Infrastructure-free peer discovery** — constellation nodes appear and disappear dynamically; no central directory
5. **Zero-trust** — every node is treated as potentially untrusted until proven otherwise

Three approaches were evaluated:
- **Option A:** TLS 1.3 with a shared PKI CA
- **Option B:** SSH tunnels with key exchange
- **Option C:** WireGuard with Ed25519 peer identity + mDNS/BLE discovery

---

## Decision

**WireGuard (Noise Protocol IK handshake) as the mesh transport. Ed25519 keys generated in Secure Enclave / TPM as node identity (hardware-bound). Peer discovery via mDNS (LAN) and DHT (WAN). Key rotation every 2 hours.**

```
     Node A (0xMeridian instance)          Node B (0xMeridian instance)
     ─────────────────────────────         ──────────────────────────────
     Ed25519 keypair (Secure Enclave)      Ed25519 keypair (Secure Enclave)
     DID: did:key:z6MkA...                 DID: did:key:z6MkB...
              │                                     │
              │   Noise_IK Handshake (1.5 RTT)      │
              │──────────────────────────────────►  │
              │  ◄──────────────────────────────── │
              │                                     │
              │   WireGuard tunnel established      │
              │   ChaCha20-Poly1305 encrypted       │
              │   ◄───────────────────────────────► │
              │                                     │
     gRPC mTLS over WireGuard tunnel                │
     Bus 4 traffic: ZK-SLA, federation messages     │
```

### Key Architecture

```rust
pub struct NodeIdentity {
    /// Ed25519 private key — never leaves Secure Enclave
    signing_key:    SecureEnclaveKey,
    /// Ed25519 public key — shareable, forms DID
    verifying_key:  VerifyingKey,
    /// Decentralized Identifier (DID)
    did:            String,  // "did:key:z6Mk..."
    /// WireGuard Curve25519 key (derived from Ed25519)
    wg_private_key: WireGuardKey,
    /// Key rotation schedule
    rotation_interval: Duration,  // default: 2 hours
}

impl NodeIdentity {
    /// Sign a constellation message — private key never leaves enclave
    pub fn sign_message(&self, msg: &[u8]) -> Ed25519Signature {
        self.signing_key.sign(msg) // in-enclave operation
    }

    /// Verify peer identity
    pub fn verify_peer(&self, peer_did: &str, msg: &[u8], sig: &Ed25519Signature) -> bool {
        let peer_vk = resolve_did(peer_did);
        peer_vk.verify(msg, sig).is_ok()
    }
}
```

### Peer Discovery Stack

```
Layer 3: Application (Ambassador Agent gRPC)
    │
Layer 2: Transport (WireGuard tunnel, ChaCha20-Poly1305)
    │
Layer 1: Discovery
    ├── LAN: mDNS (multicast DNS, no infrastructure)
    │         Service: _0xmeridian._tcp.local
    │         Advertises: {did, wg_public_key, capabilities, bus4_endpoint}
    │
    ├── BLE: Bluetooth Low Energy (mobile/IoT/no-infrastructure scenarios)
    │         GAP Advertisement: 0xMeridian service UUID + public key hash
    │
    └── WAN: Kademlia DHT (libp2p)
              Key: SHA256(did)
              Value: {wg_endpoint, public_key, last_seen}
```

### WireGuard Tunnel Parameters

```toml
[wireguard]
listen_port        = 51820
keepalive_interval = 25    # seconds — NAT traversal
handshake_timeout  = 90    # seconds before re-initiating
key_rotation_hours = 2     # ephemeral session key rotation
dns                = ""    # disabled — discovery via DID/DHT
mtu                = 1420  # standard WireGuard MTU
```

---

## Rationale

### Why WireGuard over TLS 1.3 + PKI

**TLS requires a Certificate Authority:** Either a shared CA (single point of failure, centralized trust) or a web of trust (complex certificate management). For a constellation of autonomous AI OS nodes that can appear and disappear dynamically, PKI management is operationally prohibitive.

**WireGuard's Noise_IK handshake** uses static Ed25519 keys as peer identities — no CA needed. Authenticity is established by the pre-shared public key (exchanged out-of-band via DID resolution, not a CA).

**Noise Protocol properties (from formal analysis):**
- Identity hiding (the initiator's identity is hidden from network observers)
- Perfect forward secrecy (session keys are ephemeral)
- 1.5 RTT handshake (vs 2 RTT for TLS 1.3)

### Why Ed25519 in Secure Enclave

The node's long-term identity key must be hardware-bound to prevent identity theft:
- If the key lives in memory, a compromised process can extract it
- Secure Enclave (Apple) / TPM (other platforms) ensures the private key never appears in main memory
- The DID (`did:key:z6Mk...`) is derived from the public key — deterministic, no CA required

### Why mDNS + BLE + DHT (three discovery layers)

- **mDNS:** Zero-configuration on LAN (office, datacenter), no infrastructure required
- **BLE:** For mobile and IoT scenarios where IP routing may not be available (military edge, healthcare ward)
- **DHT (Kademlia):** For WAN/multi-organization constellations where nodes are geographically distributed

Each layer is independent — the system works with any subset available.

---

## Consequences

**Positive:**
- No central Certificate Authority — constellation is fully decentralized
- Hardware-bound identities prevent key theft even under process compromise
- WireGuard <2ms overhead per hop — within Bus 4 budget
- Works without IP infrastructure (BLE discovery for air-gapped environments)

**Negative / Mitigations:**
- **WireGuard requires kernel module on Linux:** → *`wireguard-go` userspace implementation available as fallback; ~10% performance penalty*
- **mDNS does not cross network segments:** → *DHT handles WAN; mDNS is LAN-only by design*
- **Key rotation every 2h creates brief re-handshake overhead (100ms):** → *overlapping key windows prevent traffic interruption during rotation*

---

## Alternatives Rejected

| Alternative | Reason rejected |
|-------------|----------------|
| TLS 1.3 + shared CA | Centralized trust; PKI management at scale; CA compromise invalidates all certs |
| SSH tunnels | Point-to-point only; no mesh topology; management overhead |
| IPsec | Complex configuration; IKE overhead; poor NAT traversal |
| Tor onion routing | Too high latency (100–500ms); not suitable for <50ms Bus 4 requirement |
| ZeroTier | Proprietary coordination plane; requires ZeroTier central; not self-sovereign |

---

## Related

- ADR-030: Federated Constellation — WireGuard mesh is the physical substrate for Bus 4
- ADR-009: Idris 2 Security — the WireGuard handshake protocol has a formal spec verifiable against Noise Protocol invariants
- ADR-026: Cryptographic Human Override — override signals travel over Bus 4 and inherit WireGuard authentication
- TDD v5.1, Parte H: Security Threat Model — network-level threats and WireGuard mitigations
