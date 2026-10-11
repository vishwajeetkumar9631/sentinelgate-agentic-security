# Five-minute judge demo

## 0:00–0:35 — Frame the business risk

“Agents can read untrusted content and use real tools. SentinelGate is the security control plane that prevents content from silently becoming authority.” Point to **F3 target: 9/9 attack families** and state the honest depth claim: D2 verified; D3 demonstrated only if OCR is green.

## 0:35–1:30 — Show detection and neutralization

In **Live Firewall**, inspect the preloaded mixed payload. Show:

- the critical findings and provenance escalation;
- the legitimate revenue sentence preserved;
- malicious instruction chunks removed;
- the clean post-sanitization rescan.

Then click **Run end-to-end gateway**. The decisive evidence is `delivered: false` and an empty `content` field—not merely a red warning on a dashboard.

## 1:30–2:15 — Show indirect and encoded attacks

In **Attack Laboratory**, run Indirect Prompt Injection with the webpage source, then Encoded Instructions. Point out canonical extraction, recursive decode count, evidence, and route.

## 2:15–3:00 — Show stateful/agentic defense

In **Multi-Turn Defense**, lock the intent contract and run the four-turn sequence. Explain that the immutable server-side contract detects drift that no single turn fully reveals, and that the honey-canary detects context leakage on egress.

## 3:00–3:45 — Prove action enforcement

In **Tool Gate**:

1. Run Allowed knowledge search: approved.
2. Run Sensitive internal email: policy checks pass but execution remains disabled pending confirmation.
3. Run Blocked external email or shell: blocked by destination/allowlist policy.

Stress that agent-supplied permissions cannot override the server contract.

## 3:45–4:20 — Show output protection and evidence

Run **Output Guard** with the sample email and API key. Show block-and-redact. Open **Audit Center** and show the verified ledger badge plus evidence hashes.

## 4:20–5:00 — Close with measured evidence

Open **Evaluation**. State exactly:

- 1,900 transparent synthetic regression cases;
- 45 attack phrasings and 10 context wrappers;
- results are regression evidence, not a production accuracy claim;
- integration tests cover fail-closed delivery and real PDF/DOCX/EML/HTML extraction;
- the next validation gate is an independent public benchmark.

End with: “SentinelGate does not ask the agent to secure itself. It removes authority from untrusted content, enforces least privilege outside the model, and proves every decision.”
