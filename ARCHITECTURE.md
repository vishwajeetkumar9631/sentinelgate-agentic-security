# SentinelGate structural architecture

## Claimed position

SentinelGate claims **F3 implemented** and **D2 verified**, with **D3 conditional on runtime OCR readiness and live multimodal evidence**. The dashboard reports that condition instead of making an unsupported blanket claim.

## Trust-boundary flow

```text
Untrusted source
  chat | web | PDF | DOCX | email | HTML | API | code | OCR image
        |
        v
Canonical extraction
  text + hidden HTML + metadata + encoded payloads + provenance
        |
        v
Detection ensemble
  deterministic rules + semantic similarity + intent drift
  + multi-turn state + provenance escalation
        |
        v
Risk orchestrator
  ALLOW ---------> signed data-only envelope -------------------+
  QUARANTINE ----> neutralize -> rescan -> signed read-only data |
  BLOCK ---------> empty envelope + security review             |
                                                             v
                                                    downstream agent
                                                             |
                                                    proposed tool action
                                                             v
Server-side tool gate
  immutable intent contract + allowlist + strict schema + destination
  + payload safety + user authorization + step-up confirmation
                                                             |
                                                             v
Output guard -> secret / PII / prompt / honey-canary redaction
                                                             |
                                                             v
Client response + SHA-256 hash-chained evidence ledger
```

## Key decisions

1. **The LLM is not the policy authority.** Deterministic code outside the agent owns routing and tool execution.
2. **Content and instructions are separated.** The context broker labels all delivered content as data, strips capabilities, and signs the decision.
3. **Neutralization is verified.** Sanitized content is rescanned; a failed rescan is never delivered.
4. **Permissions are server-bound.** Agent-provided `allowed_actions` cannot widen an immutable session contract.
5. **High-risk actions pause.** Passing policy does not equal execution permission; email requires explicit step-up confirmation.
6. **Egress is defended.** Credential, PII, system-prompt, and session-canary leakage is blocked and redacted.
7. **Evidence is tamper-evident.** Every audit event includes the previous event hash and its own SHA-256 hash.

## Failure and recovery behavior

| Failure | Behavior |
|---|---|
| Unsupported or oversized file | Reject before inspection |
| Parser failure | Return a safe extraction error; do not pass raw bytes |
| Malicious or residual content | Block and deliver an empty envelope |
| Unknown/unallowlisted tool | Block |
| Missing authorization or schema field | Block |
| High-risk action | Require confirmation; `allowed=false` |
| Output leakage | Block and redact |
| Audit-chain mismatch | Surface failed integrity status |
| Redis unavailable | Fall back to bounded local session state |

## Evidence map to judging criteria

| Criterion | Demonstrable evidence |
|---|---|
| Significance | Prevents agent data theft and unauthorized action before execution |
| Innovation | Signed capability-free context envelopes, intent anchors, honey-canaries |
| Effective AI | Semantic classifier participates in an explainable ensemble |
| Technical execution | Multiformat extraction, recursive decoding, fusion, enforcement, egress |
| Agentic capability | Stateful intent drift, autonomous routing, tool mediation, safe recovery |
| Impact | Attack blocking, safe-content preservation, and latency metrics |
| Prototype quality | Nine judge-facing workflows and runnable APIs |
| Responsible AI | Least privilege, human confirmation, provenance, auditability, honest claims |

## Production hardening beyond the prototype

- Replace the lexical semantic baseline with a calibrated ONNX embedding classifier and an independently evaluated model.
- Move session contracts and the ledger to tenant-isolated managed storage with KMS-backed signing keys.
- Run file parsers in resource-limited sandboxes and add malware scanning.
- Add authenticated analyst review, one-time confirmation tokens, RBAC, rate limits, and SIEM export.
- Validate against an independent prompt-injection benchmark and record confidence intervals by source and attack family.
