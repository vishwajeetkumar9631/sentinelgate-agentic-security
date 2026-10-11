# SentinelGate — Prompt Injection Firewall

Working hackathon prototype for **Problem 2: Agentic Cybersecurity – Prompt Injection Firewall**. It sits before an LLM/agent, treats all inbound material as untrusted data, and returns an explainable enforcement verdict before the content can enter context or trigger a tool.

## Hackathon submission

- **Participant:** Vishwajeet Kumar
- **Event:** ET AI Hackathon: Agentic Edition, presented by Accenture
- **Project:** SentinelGate — Zero-Trust Prompt Injection Firewall
- **Pitch deck:** [PowerPoint](Vishwajeet_Kumar_SentinelGate_Pitch_Deck.pptx) · [PDF](Vishwajeet_Kumar_SentinelGate_Pitch_Deck.pdf)
- **Final narrated demo:** [Watch or download the submission video](sentinelgate_vishwajeet_hackathon_submission.mp4)

The repository contains only the final narrated submission video. Video-editing, narration-generation, and rendering scripts are intentionally excluded.

## Run

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5050`. Paste a payload or upload a `.txt`, `.md`, `.html`, `.json`, `.csv`, or text-based `.pdf`.

The dashboard now has eight judge-facing sections: Live Firewall, Attack Laboratory, Multi-Turn Defense, Tool Gate, Output Guard, Audit Center, Evaluation, and Architecture. The live view exposes adapter readiness, canonical extraction, all detection layers, nine-family coverage, exact removed chunks, preserved data, and the post-sanitization re-scan.

## Demo flow

1. Select a provenance type (user message, webpage, email, PDF, API response, source code, or OCR text).
2. Scan content. Normalization decodes HTML entities, strips null bytes, and safely inspects suspicious Base64 payloads.
3. The policy engine returns `ALLOW`, `QUARANTINE`, or `BLOCK`, a risk score, evidence, matched rules, a sanitized payload, and the downstream route.
4. Only `ALLOW` material can be presented as data to an agent. `QUARANTINE` is read-only, and `BLOCK` is routed to security review. In a production integration, the agent/tool gateway must enforce this response—not merely display it.

## Honest coverage claim

- **F3 implemented:** all nine required attack families are demonstrated (the brief requires seven).
- **D2 verified locally:** structured and unstructured text paths, enforcement, and regression evidence are runnable.
- **D3-ready, conditional:** PDF, DOCX, email, HTML, API, source-code, and image adapters exist. Claim D3 in the final submission only when the Evaluation screen reports the OCR adapter as ready and real image/PDF samples have been demonstrated. This avoids the brief's penalty for overestimation.

| Requirement | Prototype evidence |
|---|---|
| Instruction override & role change | intent/authority-change patterns |
| Secret extraction & credential theft | secret/credential + disclosure action correlation |
| Tool abuse | tool invocation + high-impact action correlation |
| Context poisoning & indirect injection | provenance-aware escalation and hidden-HTML detection |
| Multi-step jailbreak | ordered-step attack patterns |
| Encoded instructions | Base64 detection and safe decode-for-inspection |
| Reliability and auditability | deterministic policy decisions, evidence, confidence, provenance, and sanitized output |

The UX accepts all named source categories. It extracts text from PDFs, DOCX, EML email, HTML (including comments, metadata, attributes and hidden/script content), source/API text, and images through an OCR adapter. Install Tesseract plus `pytesseract` locally (or configure PaddleOCR) to activate image OCR. Redis is used for persistent multi-turn session state when `REDIS_URL` is available; the demo safely falls back to a concurrency-safe local SQLite state store.

Additional enforcement endpoints are available for an agent integration: `POST /api/tool-call` validates an authorized, allowlisted tool request and strict arguments; `POST /api/output-check` redacts detected credentials and system-prompt disclosure; `GET /api/audit` returns the recent audit trail.

`POST /api/context-broker` is the protected handoff boundary. It never returns blocked content to the downstream agent; allowed or safely neutralized content is wrapped as non-instructional data with no tool capabilities and an HMAC signature. Set `SENTINELGATE_SIGNING_KEY` in any non-demo deployment. Tool permissions are read from the immutable server-side intent contract, not from agent-controlled request fields, and high-risk actions remain non-executable until step-up confirmation.

Audit events are chained with SHA-256 evidence hashes. `GET /api/audit/integrity` verifies the full ledger and the Audit Center exposes the result and each event hash.

## Advanced runtime security

- `POST /api/intent-anchor` creates an immutable session contract containing declared intent, allowed actions, prohibited actions, and a unique honey-canary. A later prompt that semantically drifts to a prohibited action is blocked.
- The semantic classifier uses transparent cosine similarity against all nine attack families. It is deliberately adapter-shaped so an ONNX embedding model can replace it in deployment.
- Pass `session_id` to `POST /api/output-check`; a returned session canary is blocked and redacted as an egress incident.
- Run `python benchmark.py` for a repeatable adversarial/benign test run. It reports attack recall, safe-content preservation, P50 and P95 firewall latency using recorded values.

The bundled synthetic regression protocol generates 100 cases for each of the nine attack categories plus 1,000 benign cases (1,900 total), using 45 attack phrasings and 10 context wrappers. Results are saved to `benchmark_results.json` and appear in the Evaluation screen. These transparent synthetic results are regression evidence only; the UI and report explicitly require independent external benchmark validation before any production accuracy claim.

Run the integration suite with `python -m unittest -v test_sentinelgate.py`. It covers direct and encoded attacks, fail-closed agent handoff, signature verification, server-bound tool permissions, human confirmation, output redaction, audit integrity, and HTML/EML/DOCX/PDF adapters.

## Production architecture

```text
Source adapters (chat / RAG / mail / OCR / API / file)
        │  immutable source ID, tenant, trust label, hash
        ▼
Normalizer → canonical text + hidden-content extraction + encoded-payload inspection
        ▼
Detection ensemble → deterministic policy / ML classifier / LLM judge (structured JSON)
        ▼
Risk orchestrator → ALLOW | QUARANTINE | BLOCK + evidence + signed decision
        ├──► append-only security audit / SIEM
        ├──► analyst feedback queue (false-positive tuning)
        └──► Agent Context Broker → tool-permission gate → agent
```

Security controls for a real deployment: content size/time limits; sandboxed parsers; SSRF-safe retrieval; tenant isolation; no secrets in LLM context; least-privilege, user-confirmed tool calls; immutable logs; rule/model versioning; adversarial regression suite; and human review for high-risk/low-confidence decisions.
