# Proyecto Final — Inteligencia Artificial

**Autores:**  
Juan Andrés Loncharich, Legajo 14534  
Diego Alejandro Forni, Legajo 14329

**Repositorio:** https://github.com/JuanLoncharich/proyecto_delfin  
**Universidad Nacional de Cuyo — Ingeniería en Sistemas de Información**

---

## 1. Introducción

The proliferation of autonomous software agents driven by Large Language Models (LLMs) is rapidly transforming the cybersecurity landscape. Traditional intrusion detection systems (IDS) are effective at identifying anomalous traffic patterns, but their response pipelines remain fundamentally human-in-the-loop: an alert is generated, a human analyst evaluates it, and a human operator applies a countermeasure. This chain introduces latency that can be critical — modern brute-force and credential-stuffing attacks execute hundreds of attempts per second, and even a ninety-second response window may be sufficient for an attacker to successfully authenticate and establish persistence.

At the same time, the availability of LLMs capable of reasoning about network telemetry, generating executable shell commands, and adapting their strategy in real time opens the possibility of a new class of defensive agent: one that reads IDS alerts, formulates a remediation plan in natural language, and executes that plan autonomously on the affected hosts — all within seconds of the initial detection. This is not a hypothetical capability; the tooling required to build such a system (open IDS platforms, LLM APIs, autonomous coding agents) is widely available today.

The challenge, however, is empirical: it is not known whether LLM-based defenders actually work in adversarial conditions, how they fail, and whether the emergent behaviors they produce are safe and predictable. Existing evaluations of LLM agents in cybersecurity are largely one-sided — they test offensive capabilities (exploit generation, vulnerability discovery, code deobfuscation) in isolation, without a live, adapting defender [1][2][3]. No reproducible open framework exists for simultaneously running attack and defense LLM agents and observing their interaction.

This work presents **Trident**, a minimal Docker-based cyber range designed specifically to address that gap. Trident instantiates two isolated subnets connected through a routing layer, places a protected server on one side and a compromised host on the other, and runs three simultaneous agent types: an attacker (coder56, powered by an LLM coding agent), a defender (SLIPS IDS plus an LLM auto-responder), and a benign traffic generator (db\_admin) that introduces realistic background noise. All traffic between subnets is captured deterministically via a central router and fed to the IDS in near-real-time, producing fully reproducible per-run artifacts (PCAP files, structured JSONL timelines, IDS alert logs) suitable for automated downstream analysis.

The main research objective is to measure — in controlled, reproducible conditions — whether an LLM-based defender can detect and mitigate attacks in real time, what failure modes it exhibits, and what emergent attacker-defender interactions arise when both sides reason autonomously from the same network signals. Secondary objectives include characterizing the cost structure of LLM-based defense (in tokens and latency) and identifying the systemic vulnerabilities that arise when an autonomous agent applies firewall rules to its own execution environment.

This document is structured as follows. Section 2 covers the theoretical background: LLMs, autonomous coding agents, and the SLIPS IDS platform. Section 3 describes the experimental design in detail, including the infrastructure, metrics, and the three experiment categories conducted. Section 4 presents and analyzes the results from nine combined-agent runs. Section 5 draws conclusions and identifies future work.

---

## 2. Marco Teórico

### 2.1 Large Language Models and Their Application in Cybersecurity

Large Language Models are neural networks trained on massive text corpora using self-supervised objectives (primarily next-token prediction) at a scale sufficient to produce emergent reasoning capabilities [1]. The key architectural component is the Transformer, introduced by Vaswani et al. in 2017, which uses multi-head self-attention to model long-range dependencies between tokens without recurrence. Models at the scale of tens to hundreds of billions of parameters exhibit in-context learning: the ability to adapt their behavior to a task described in natural language, without any weight updates, purely from the examples and instructions provided in the prompt.

The relevance of LLMs to cybersecurity was recognized early in the literature and has grown substantially since the release of highly capable models. A systematic review by [1] identifies four main application domains: (a) vulnerability detection and code analysis, (b) threat intelligence summarization, (c) malware and exploit generation, and (d) autonomous attack and defense agents. The survey across 180 papers finds that while LLMs are effective at the first three tasks, autonomous defense agents remain largely under-studied and under-benchmarked. Most existing evaluations either test offensive LLM agents without a live defender, or evaluate defensive capability on static datasets without an active attacker.

A 2025 survey by [2] reinforces this finding and adds that the state-of-the-art in LLM-based cybersecurity is characterized by two persistent gaps: reproducibility and adversarial simultaneity. Studies that test LLM defenders do so against scripted, replay-based attacks rather than against a live adversarial agent that can detect and adapt to the defense. This work directly addresses both gaps through the Trident framework.

From a safety perspective, [3] notes that LLM-based security agents introduce unique vulnerabilities including prompt injection (an attacker embedding malicious instructions in network payloads that the defender LLM reads), goal misalignment (the agent optimizing for a proxy objective rather than actual security), and catastrophic self-interference (the agent applying rules that sever its own control channel). All three of these failure modes were observed in the experiments described here.

### 2.2 Autonomous Coding Agents and OpenCode

An autonomous coding agent is an LLM that is given access to a tool set — at minimum, a shell — and is tasked with achieving a goal expressed in natural language. The agent reasons in a loop: it calls a tool, observes the output, updates its internal state, and decides the next action. This loop continues until the agent judges the goal complete or a timeout is reached. OpenCode [4] is an open-source implementation of this pattern specifically designed for software engineering and system administration tasks. It exposes an HTTP API that accepts a natural-language goal and returns a streaming JSON event stream containing the agent's reasoning steps, tool calls, and outputs. In Trident, OpenCode is used for both the attacker (coder56) and the defender (auto-responder): the attacker runs OpenCode on the compromised host and is given an offensive goal, while the defender's auto-responder calls OpenCode on the target server with a remediation plan generated by the LLM planner.

This architecture separates two concerns: *planning* (the LLM planner reads the IDS alert and produces a structured, validated remediation plan in JSON) and *execution* (OpenCode reads the plan and translates it into shell commands on the affected host). The planner is constrained to produce only a natural-language plan with specific firewall constraints; it does not directly execute code. This separation is intended to reduce the risk of prompt-injection attacks reaching the execution layer without review, and to allow the plan to be validated against a JSON schema before execution.

### 2.3 SLIPS: Stratosphere Linux IPS

SLIPS (Stratosphere Linux IPS) [5] is an open-source network intrusion detection system developed at the Stratosphere Research Laboratory, Czech Technical University in Prague. It is designed to operate on traffic in PCAP format or directly on network interfaces, and uses a combination of machine learning models and rule-based detectors organized into detection modules. Relevant modules for this work include:

- **PortScan**: detects horizontal and vertical port scans based on the number of distinct destination ports or hosts contacted within a time window.
- **PasswordGuessing**: detects SSH and HTTP brute-force attempts based on repeated authentication failures from a single source.
- **ARP poisoning**, **DNS anomalies**, and **data exfiltration** modules were also active but not the primary focus of the main experiments.

SLIPS outputs alerts in JSON format with a threat level (info, low, medium, high, critical) and a detection description. Only HIGH and CRITICAL alerts are processed by the auto-responder to reduce false-positive-driven defensive actions. SLIPS runs inside the `lab_slips_defender` container and reads the rotating PCAP files generated by the router, introducing a latency of up to one PCAP rotation interval (30 seconds) between traffic generation and alert emission.

### 2.4 Reinforcement Learning from Human Feedback and Instruction Following

A key property that distinguishes instruction-following LLMs from base pre-trained models is alignment training — specifically, Reinforcement Learning from Human Feedback (RLHF) and its variants (RLAIF, DPO). These training procedures teach the model to follow instructions reliably, refuse harmful requests, and produce outputs in structured formats like JSON when asked. For incident response planning, this property is essential: the planner must not only understand the security alert (a comprehension task) but also produce a JSON object with specific keys in a specific format, under a system prompt that includes hard firewall constraints. Without alignment training, base models frequently produce outputs with inconsistent structure or ignore explicit constraints in the prompt. The degree to which alignment training transfers reliably to novel constrained-output tasks like JSON plan generation under adversarial conditions is itself an open empirical question, and is one of the factors that explains the failure modes observed in Section 4.

### 2.5 Incident Response Planning with LLMs

The planner component receives a raw SLIPS alert and generates a structured remediation plan using a carefully engineered system prompt (stored in `prompts.yaml`). The prompt instructs the model to:

1. Identify the executor host (the machine where the defensive action should run), the attacker IP, and the attack type.
2. Produce an immediate containment plan, including specific iptables rules, SSH configuration changes, and optionally deception strategies.
3. Include a `COMPLETION` section with verifiable criteria that the executing agent can use to confirm the remediation succeeded.
4. End the plan with the literal token `END_OF_PLAN` so the executor agent knows when to stop.

Critically, the prompt includes hard constraints on firewall rules: the planner must never suggest blocking SSH (port 22), HTTPS (port 443), or the OpenCode control port (4096), since doing so would sever the agent's own execution capability. The consequences of violating these constraints — observed directly in the experiments — are discussed in Section 4.

---

## 3. Diseño Experimental

### 3.1 Infrastructure: The Trident Cyber Range

All experiments were conducted in Trident, a Docker Compose-based cyber range that creates a fully isolated, deterministically observable network environment. The topology consists of three Docker bridge networks:

- `lab_net_a` (172.30.0.0/24): the attacker subnet, containing `lab_compromised` (172.30.0.10).
- `lab_net_b` (172.31.0.0/24): the defender subnet, containing `lab_server` (172.31.0.10).
- `lab_egress` (172.32.0.0/24): internet egress for the router and defender only; `lab_compromised` and `lab_server` have no direct internet access.

All traffic between the two lab subnets is forced through `lab_router` by overriding the default routes of both lab hosts at container startup. The router runs `tcpdump` on the LAN-A interface, producing rotating PCAP files every 30 seconds into `outputs/<RUN_ID>/pcaps/`. A simultaneous continuous capture runs on `lab_server`'s interface. This architecture guarantees that every packet crossing between subnets appears in the PCAP corpus — there is no path that bypasses the router.

| Container | IP(s) | Role |
|---|---|---|
| `lab_router` | 172.30.0.1, 172.31.0.1 | Inter-subnet routing, PCAP capture, DNS forwarder |
| `lab_server` | 172.31.0.10 | Protected target: PostgreSQL 15, OpenSSH, nginx, Flask login app |
| `lab_compromised` | 172.30.0.10 | Attacker platform: nmap, hydra, sshpass, OpenCode, rockyou.txt |
| `lab_slips_defender` | 172.30.0.30, 172.31.0.30 | SLIPS IDS + LLM auto-responder |
| `lab_dashboard` | (dashboard_net) | FastAPI + React monitoring UI |

The lab server exposes three services: an nginx reverse proxy with a Flask-based login application (port 80), SSH (port 22), and PostgreSQL (port 5432). The login application logs every authentication attempt (username, password length, source IP, timestamp, success) to a structured JSONL file, enabling precise measurement of attack progress independent of network-layer observations.

To simulate data exfiltration without real external connectivity, the router installs a DNAT rule that redirects traffic destined for a fake public IP (137.184.126.86:443) to a local netcat listener on the router itself, which writes the received bytes to a log file. This allows the attacker agent to "exfiltrate" database dumps to a seemingly external address while keeping all data within the lab.

### 3.2 Metrics

Five primary metrics were defined to evaluate defender performance:

| Metric | Definition | Unit |
|---|---|---|
| `t_alert` | Time from first attack packet to first HIGH/CRITICAL SLIPS alert processed by auto-responder | seconds |
| `t_decision` | Time from first alert to LLM planner returning a validated remediation plan | seconds |
| `t_exec` | Time from plan generation to OpenCode confirming execution on target host | seconds |
| `t_blocked` | Total elapsed time from attack start to service confirmed blocked | seconds |
| `password_found` | Whether the attacker successfully authenticated before being blocked | bool |

Two secondary metrics were tracked for cost and efficiency analysis:

- **Token usage per agent per run**: input tokens, output tokens, reasoning tokens, and cache reads, disaggregated for the attacker, defender (server-side), defender (compromised-side), and benign agent.
- **Alert volume**: number of HIGH/CRITICAL alerts processed by the auto-responder per run.

### 3.3 Experiment Categories

Three experiment categories were designed, each targeting a distinct attack scenario:

**Category A — Flask Web Brute Force.** The attacker performs an nmap network and port discovery scan, then launches an HTTP password-spraying attack against the Flask login page using a 1,000-entry wordlist with the correct password inserted at a random position. The defender is expected to detect the port scan (PortScan alert from SLIPS) and/or the HTTP brute force (PasswordGuessing alert), generate a blocking plan, and execute it before the attacker finds the correct password. The experiment terminates when the Flask port becomes blocked (3 consecutive connection failures observed by the monitoring script) or after a 15-minute timeout.

**Category B — Database Exfiltration.** The attacker connects to the PostgreSQL instance on `lab_server`, dumps the database, and transfers the dump to the simulated external IP. SLIPS is expected to detect the large outbound data transfer and the defender is expected to block the connection before the dump completes. Success is measured by comparing the bytes received at the router's netcat listener against the full database size.

**Category C — Combined Agents.** The most complex scenario: the attacker, defender, and benign agent run simultaneously. The attacker receives an open-ended goal ("find and compromise the server on the network"), the defender responds to SLIPS alerts in real time, and the benign agent generates legitimate PostgreSQL and web traffic in parallel. This scenario tests the defender's precision (does it block only the attacker, not the benign agent?) and reveals emergent attacker-defender interactions that do not appear in isolated experiments.

### 3.4 Tools and Configuration

| Tool / Framework | Version | Purpose |
|---|---|---|
| Docker Engine | 27.0 | Container lifecycle |
| Docker Compose | v2 | Multi-container orchestration |
| SLIPS | 1.0.14 (custom patched) | Network IDS, alert generation |
| Zeek | 6.x (via SLIPS) | Protocol parsing for PCAP analysis |
| OpenCode | 0.3.x | LLM coding agent runtime |
| LLM API | gpt-oss-120b via e-INFRA CZ | LLM provider for all agents |
| nmap 7.94 | — | Port and host discovery (attacker) |
| hydra 9.4 | — | SSH/HTTP brute-force (attacker) |
| FastAPI | 0.110 | Defender REST API, dashboard backend |
| React 18 + Tailwind | — | Monitoring dashboard frontend |
| Python 3.12 | — | Experiment runners, analysis scripts |
| matplotlib + seaborn | — | Results visualization |

SLIPS was patched in three places to function correctly in the lab environment: the Zeek local profile was adjusted to use the correct lab interface naming, the HTTP analyzer module was modified to avoid false-positive PasswordGuessing alerts on the lab's own Flask application's health checks, and the flowalerts evidence module threshold for SSH brute-force was tuned from the default (20 failures) to 5 failures to reduce detection latency in experiments with limited attempt counts.

### 3.5 Combined Agents Experiment Results

Nine combined-agent runs were conducted across two dates (March 19–20, 2026). Each run was initialized from a clean container state with a new `RUN_ID`. The attacker's goal in all runs was to find and compromise the server; the defender responded autonomously to SLIPS alerts; the benign agent (when present) ran a PostgreSQL administration workload with 60–130 second sleep intervals between tasks.

**Table 1: Combined Agent Run Summary**

| Run | Date/Time | Benign | Defender Status | Attacker Tokens | Notable Result |
|-----|-----------|--------|-----------------|-----------------|----------------|
| 1 | 20260319_211825 | No | Both active | 3.9M | Attacker probes OpenCode control port (4096); detects rate-limiting and pivots |
| 2 | 20260319_215344 | Yes | Both active | 0.65M | 10× token amplification; zero false positives on benign traffic |
| 3 | 20260319_222827 | Yes | Server only | 8.4M | Defender compromised-side silent; attacker runs unopposed for most of run |
| 4 | 20260319_231420 | Yes | Both active | 1.9M | All three agents coexist; HTTP brute force detected in batch |
| 5 | 20260319_234448 | No | Both active | 0.16M | Attacker terminates early; minimal interaction |
| 6 | 20260320_000226 | No | Server only | 12.2M | Defender applies self-blocking OUTPUT rule; attacker outlasts defender |
| 7 | 20260320_004808 | No | Zero responses | 8.2M | Defender total outage at peak alert volume (116 alerts; 0 responses) |
| 8 | 20260320_013351 | No | Both active | 1.2M | Defender independently invents honeypot and fake credential files |
| 9 | 20260320_021543 | No | Both active | — | Defender deploys multi-port honeypot; attacker falls for it and is tracked |

**Table 2: Attacker Token Usage Statistics**

| Statistic | Value |
|---|---|
| Median attacker tokens (all runs) | ~2.0M |
| Minimum | 0.16M (run 5, early termination) |
| Maximum | 12.2M (run 6, exhaustive enumeration loop) |
| Runs where defender was fully active (both instances) | 6 / 9 |
| Runs with zero false positives on benign traffic | 3 / 3 (all runs with benign agent) |
| Runs with defender outage or self-block | 3 / 9 (runs 6, 7, and partially 3) |

**Table 3: Defender Failure Modes Observed**

| Failure Mode | Observed In | Cause |
|---|---|---|
| Benign agent startup failure | 6 / 9 runs | Race condition: attacker claims OpenCode session first |
| API rate limit cascade | Runs 1, 6 | 4 parallel request limit shared across all agents |
| Defender self-blocking (OUTPUT rule) | Run 6 | LLM planner violated firewall constraint from system prompt |
| Defender total outage | Run 7 | OpenCode API unavailable; auto-responder failed silently |
| Prompt/plan contradiction loop | Runs 1, 3 | Attacker targets port 4096; defender cannot block it |

---

## 4. Análisis y Discusión de Resultados

### 4.1 General Defender Effectiveness

The defender was partially or fully active in 8 of the 9 combined-agent runs. In the three runs where the benign agent also operated, SLIPS generated **zero false-positive alerts** attributing benign traffic to the attacker. This is a meaningful positive result: SLIPS maintained precision under mixed-traffic conditions, correctly attributing all alerts to the attacker's subnet (172.30.0.10) despite simultaneous legitimate PostgreSQL connections and outbound web requests from the benign agent. This demonstrates that SLIPS's behavioral detection is sufficiently specific to distinguish a brute-force pattern from realistic database workloads, even when both originate from the same compromised host subnet.

However, the defender's effective response rate was substantially below 100%. In three of nine runs (33%), the defender either produced zero responses (run 7) or applied a self-defeating firewall rule that disconnected itself mid-execution (run 6). These are not minor edge cases — run 7 occurred at the highest alert volume in the dataset (116 alerts), precisely the condition under which the defender most needed to function. The implication is that the system's robustness under load is a primary open problem.

### 4.2 The Token Amplification Effect

One of the most significant findings is what we term the **token amplification effect**: a low-cost attack generates a disproportionately expensive defensive response. In run 2, the attacker used 650K tokens — one of its lowest counts, indicating a relatively limited enumeration effort. The defender server, however, consumed 7.8M tokens in the same run — more than 12× the attacker's cost. The cause is structural: a horizontal port scan (in which the attacker contacts progressively more distinct IPs) generates a SLIPS PortScan alert each time a new threshold is crossed (5 → 20 → 35 → 51 → 67 destination IPs). Each alert triggers a full planner + executor LLM cycle. The attacker pays for one scan; the defender pays for every threshold it crosses.

This asymmetry has practical implications for any deployment of LLM-based defense at scale. If the defender runs on the same cost structure as the attacker (a shared API budget), a sustained, low-effort attacker can exhaust the defender's resources before causing any real damage. Rate-limiting defensive LLM calls (perhaps by deduplicating alerts within a short window, already partially implemented via `DUPLICATE_DETECTION_WINDOW=300`) is necessary but not sufficient; the core problem is that SLIPS generates multiple alerts for a single logical attack event.

### 4.3 Emergent Behaviors: Honeypots and Deception

The most striking finding from the combined experiments is the defender's spontaneous deployment of deception infrastructure, which was not explicitly specified in the system prompt. The system prompt instructs the planner to "not limit to normal remediation plans, include deception, counter attacks" — but the specific implementation was entirely emergent from the LLM's interpretation of that directive.

In run 8, the defender independently created what it described as a "Honeyport (8888) — Wastes attacker time with slow responses," along with fake credentials files with access logging and fake DNS entries pointing to non-existent hosts. In run 9, this strategy evolved: the defender deployed a multi-layer system including five fake services on ports 80, 443, 3000, 5000, 4443, 8080, 8888, and 9999, each with a distinct purpose (beacon server for C2 simulation, fake exfiltration endpoint, false-flag server returning fake "compromised" data). The defender's stated intent was explicit:

> *"Instead of just blocking, we've actively created fake services that: Log every connection attempt, Return false 'success' indicators, Allow attackers to think they're succeeding while being tracked."*

The attacker fell for this in run 9. After encountering the honeypot's misleading responses, the attacker attributed the behavior to infrastructure failure rather than active deception:

> *"The server seems to be unresponsive. Let me check the other hosts more carefully."*

The attacker never detected the honeypot. It interpreted misleading responses as network problems and shifted its search to other potential targets, spending substantial time interacting with honeypot endpoints and generating telemetry the defender was silently collecting. This is a cognitively realistic deception: humans and LLMs alike tend to apply Occam's razor and attribute unexpected behavior to mundane causes (network errors, overload) before considering active deception. The LLM attacker's failure to model an adversary was exploited by the LLM defender.

### 4.4 The Control Port Paradox

In run 1, SLIPS generated a `PasswordGuessing` alert for repeated HTTP requests from the attacker to `172.31.0.1:4096/session/[SESSION_ID]/abort`. Port 4096 is the OpenCode API — the control channel through which the defender receives and executes its plans. The attacker discovered this port during service enumeration and began probing it.

The system prompt explicitly prohibits blocking port 4096, because doing so would terminate the defender's own execution capability. This created a genuine security paradox: the attacker found the defender's single point of failure, and the defender literally cannot close it. All plans generated for this alert skipped the step of blocking port 4096, leaving the attacker free to probe the control channel for the entire run. The attacker did not capitalize on this (it was not trying to abort the defender session, just performing service enumeration), but the structural vulnerability is real and reproducible.

This finding reveals a fundamental architectural limitation of the system as designed: an autonomous agent that enforces firewall rules on its own execution environment cannot protect its own control channel. Any sufficiently comprehensive port scan will discover the control port, and the constraint preventing its closure is non-negotiable for the system's continued operation.

### 4.5 Attacker Adaptation to Defensive Actions

In run 1, after the defender applied rate-limiting rules, the attacker never received an explicit "blocked" message — only timeouts and connection failures. The attacker's response was goal-directed reasoning about an inferred adversary:

> *"The server might have blocked my IP or is overloaded. Let me try a different approach."*

The attacker then switched from HTTP to HTTPS endpoints, searched for exposed configuration files that might reveal credentials, and pivoted to scanning additional subnets. This adaptation occurred within a single reasoning loop, with no human guidance. The attacker inferred the existence of a defense from the pattern of failures and updated its attack model accordingly. This is more sophisticated than simple retry logic and represents a level of adversarial adaptability that is qualitatively different from scripted attack tools.

Notably, however, the attacker never succeeded in authenticating to any service across all nine runs. The LLM attacker consistently remained in the reconnaissance phase: finding the login form, attempting a wordlist brute-force via HTTP, hitting repeated 401 responses, and looping back to scanning. It never tried default credentials (admin/admin, root/root), never installed a dedicated brute-force tool (hydra, medusa), and never pivoted from HTTP to SSH when HTTP failed. This suggests that the LLM's "attacker behavior" is bounded by its training distribution — common attack patterns are represented, but methodical, goal-directed exploitation that requires multi-step planning beyond the immediate observation was not exhibited. The system prompt for the attacker was improved after these observations (adding explicit instructions to try default credentials first and to pivot to SSH if HTTP fails), but the improved prompt was not yet used in the runs reported here.

### 4.5b Attacker Failure to Escalate Beyond Reconnaissance

A consistent pattern across all nine runs is that the attacker agent (coder56) never succeeded in authenticating to any service. Despite discovering the Flask login page, the attacker's brute-force attempts were limited to sequential HTTP POST requests using a generic wordlist via curl, without trying obvious default credentials (admin/admin, root/root, labuser/labpass) or switching to a dedicated brute-force tool like hydra. When HTTP failed, the attacker searched for credential leaks in exposed files and pivoted to scanning other hosts, but never systematically escalated.

This behavioral boundary is likely an artifact of the LLM's training distribution. The model generates plausible next-action sequences for common attack patterns, but systematic, multi-stage attack planning that requires reasoning across multiple failure modes ("HTTP brute force failed → try SSH → try default credentials → try credential stuffing with harvested usernames") requires a form of goal persistence and structured state management that the current coder56 system prompt does not enforce. This is addressable through prompt engineering (adding explicit stage transitions and fallback strategies to the goal specification) and was identified as a priority fix for future experiment iterations.

### 4.6 Limitations of the Experimental Setup

Several limitations must be acknowledged when interpreting these results:

**PCAP rotation latency.** The 30-second PCAP rotation interval introduces a structural delay of up to 30 seconds between traffic generation and SLIPS alert emission. This means `t_alert` has a hard floor of ~30 seconds, which does not reflect an inherent LLM limitation but an architectural parameter of the lab. In a production deployment with streaming analysis, this latency would be much lower.

**Shared API key rate limiting.** Three simultaneous LLM agents sharing a single API key with a 4-parallel-request limit created artificial contention that caused failures in multiple runs. This is an infrastructure constraint, not a fundamental limitation of LLM-based defense. Separating API credentials per agent type would eliminate this failure mode.

**Single LLM provider.** All agents used the same model (gpt-oss-120b via e-INFRA CZ). The results are therefore specific to this model family's capabilities and limitations. A GPT-4-class model might produce more reliable firewall rule generation (reducing self-blocking events), but might also be more expensive per token. Model choice should be evaluated as a variable in future work.

**Controlled lab environment.** The lab network is small (two hosts, two subnets) and entirely Docker-managed. Real enterprise networks have orders of magnitude more hosts, services, and traffic patterns. The behavioral results from this lab (honeypot deployment, control port paradox, token amplification) are hypotheses about real-world behavior, not demonstrated in-production findings.

**Absence of lateral movement.** The attacker was constrained to a single compromised host and never moved laterally to other systems. Real advanced persistent threat (APT) actors commonly use the initial compromised foothold to pivot into adjacent subnets, escalate privileges, and establish persistence mechanisms that survive reboots. The Trident architecture supports adding additional internal hosts to simulate this, but lateral movement experiments were out of scope for this project.

**Deterministic wordlist.** The brute force experiments used a 1,000-entry wordlist with the correct password at a random position. This is an artificial simplification: real password-spraying attacks use much larger lists, adapt their strategy based on observed lockout policies, and may use credential databases from prior breaches. The lab's controlled wordlist ensures the experiment terminates predictably, but underestimates the complexity of real brute-force scenarios.

---

## 5. Conclusiones Finales

This work demonstrates that an LLM-based autonomous defender, integrated with a state-of-the-art IDS (SLIPS) and an autonomous coding agent (OpenCode), is technically feasible and produces measurable defensive effects in a controlled lab environment. Across nine combined-agent runs, the following conclusions can be drawn:

**What worked.** The SLIPS + LLM planner + OpenCode execution pipeline successfully detected attacks, generated remediation plans, and applied firewall rules on the target host in the majority of runs. The defender spontaneously invented deception strategies (honeypots, fake credential files) that successfully misled the attacker without any explicit instruction to use these specific techniques — an emergent capability that exceeded the explicit design specification. SLIPS maintained zero false positives across all three runs where a benign agent was active, demonstrating acceptable detection precision under mixed-traffic conditions.

**What failed.** The system failed in approximately one third of runs due to infrastructure and prompt engineering issues: defender outage under peak alert load (run 7), self-inflicted firewall blocking (run 6), and benign agent startup race conditions (6/9 runs). These are not fundamental LLM limitations but engineering problems with known, implementable fixes: retry logic on session creation, deduplication of SLIPS alerts before they reach the planner, and an explicit exception in the system prompt for the case where the attacker targets the control port.

**Structural finding: the token amplification effect.** The cost asymmetry between attacking and defending — where a low-effort attack generates a high-cost defensive response — is a structural property of the system that has significant implications for scalability. An adversary aware of this can exhaust defensive API budgets without mounting a serious attack. Budgeted per-alert planning with circuit-breaker fallback to rule-based responses is a necessary complement to LLM-based defense.

**Future work.** Several experiments were designed but not completed within the scope of this project:

- *Adversarial prompt injection*: embedding malicious instructions in network payloads (HTTP headers, DNS TXT records) that the defender's LLM reads as part of the alert context. A preliminary DNS entropy injection experiment was designed (`scripts/defender_experiments/injection/`) but not fully evaluated.
- *Multi-round adaptive attacks*: an attacker that explicitly models the defender's behavior from observed blocking events and adapts its strategy to avoid triggering SLIPS detection. The current attacker shows limited adaptation; a more sophisticated goal specification would push this further.
- *Model comparison*: evaluating the same architecture with different LLM models (GPT-4o, Claude 3.5 Sonnet, Llama 3.1 70B) to characterize the relationship between model capability, defense quality, and cost.
- *Formal latency measurement*: the three latency metrics (`t_alert`, `t_decision`, `t_exec`) were computed for the brute force experiments but their distributions across a larger N (≥30 runs) would enable statistical characterization of the pipeline's responsiveness.

An important methodological note: the experiment analysis and the identification of notable interactions described in Section 4 were performed using both manual inspection of the structured JSONL timelines and an LLM-assisted analysis script (`generate_brute_force_analysis.py`) that sent execution traces to an LLM and asked it to identify the most unexpected action in each run. This meta-use of an LLM to analyze the behavior of other LLMs produced consistent, useful summaries but also highlights the challenge of evaluation in this domain: the evaluator and the system under evaluation share the same capabilities and potential blind spots. Future work should include human expert review of a random sample of runs to validate the LLM-generated summaries.

The central contribution of this work is Trident itself: a reproducible, open-source cyber range that makes it possible to run these experiments without hypervisor dependencies, with deterministic traffic capture and structured per-run artifacts. The code is available at the repository listed above and is designed to be extended with new attack scenarios, new agent types, and alternative LLM providers.

Beyond Trident as infrastructure, this work contributes three empirical findings to the broader question of LLM-based autonomous defense: (1) emergent deception behaviors — honeypots, fake credentials, misleading service responses — can arise from a single directive in the system prompt and can be effective against an LLM attacker that does not model active deception; (2) the token amplification effect is a structural cost problem that requires architectural solutions (alert deduplication, per-alert budgeting, circuit-breaker fallback) rather than just better prompting; and (3) the control port paradox — an agent that applies firewall rules to its own execution environment cannot protect its own control channel — is a fundamental architectural constraint that requires a separated, hardened channel for defensive operations in any production deployment. These findings are directly relevant to the broader research agenda of safe, reliable LLM-based autonomous agents [7][8].

---

## Bibliografía

[1] Ferrag, M. A., Haelterman, R., & Cordero, C. G. (2024). *Large Language Models for Cyber Security: A Systematic Literature Review.* ACM Computing Surveys. https://dl.acm.org/doi/10.1145/3769676

[2] Motlagh, F. N., Hajizadeh, M., Majd, M., Najafipour, M., Javidan, R., & Mahdian, B. (2025). *Large Language Models in Cybersecurity: State-of-the-Art.* In Proceedings of the 11th International Conference on Information Systems Security and Privacy (ICISSP 2025). SCITEPRESS. https://www.scitepress.org/Papers/2025/133776/133776.pdf

[3] Chen, H., Zheng, Y., Guo, X., Deng, G., Liu, Y., Li, T., Zhang, Y., & Wang, H. (2025). *Large Language Models in Cybersecurity: A Survey of Applications, Vulnerabilities, and Defense Techniques.* AI, 6(9), 216. MDPI. https://www.mdpi.com/2673-2688/6/9/216

[4] OpenCode Contributors. (2024). *OpenCode: An open-source autonomous coding agent.* GitHub. https://github.com/sst/opencode

[5] Stratosphere Research Laboratory. (2023). *SLIPS: Stratosphere Linux IPS.* Czech Technical University in Prague. https://github.com/stratosphereips/StratosphereLinuxIPS

[6] Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., & Polosukhin, I. (2017). *Attention is all you need.* Advances in Neural Information Processing Systems, 30.

[7] Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). *Generative agents: Interactive simulants of human behavior.* In Proceedings of the 36th Annual ACM Symposium on User Interface Software and Technology.

[8] Shinn, N., Cassano, F., Labash, B., Gopinath, A., Narasimhan, K., & Yao, S. (2023). *Reflexion: Language agents with verbal reinforcement learning.* Advances in Neural Information Processing Systems, 36.

---

## Apéndice A: Arquitectura del Sistema

```
┌──────────────────────────────────────────────────────┐
│                    lab_net_a (172.30.0.0/24)          │
│  ┌─────────────────┐                                  │
│  │ lab_compromised │  172.30.0.10                     │
│  │ (attacker)      │  nmap, hydra, OpenCode           │
│  └────────┬────────┘                                  │
└───────────┼──────────────────────────────────────────┘
            │  (all traffic forced through router)
┌───────────┼──────────────────────────────────────────┐
│           ▼                                           │
│  ┌─────────────────┐                                  │
│  │   lab_router    │  172.30.0.1 / 172.31.0.1         │
│  │                 │  tcpdump → outputs/RUN_ID/pcaps/  │
│  └────────┬────────┘                                  │
└───────────┼──────────────────────────────────────────┘
            │
┌───────────┼──────────────────────────────────────────┐
│           ▼          lab_net_b (172.31.0.0/24)        │
│  ┌─────────────────┐                                  │
│  │   lab_server    │  172.31.0.10                     │
│  │ (protected)     │  PostgreSQL + SSH + nginx/Flask   │
│  └─────────────────┘                                  │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│  lab_slips_defender  (172.30.0.30, 172.31.0.30)       │
│                                                       │
│  SLIPS IDS ──reads──▶ PCAPs                          │
│       │                                               │
│       ▼ alert (HIGH/CRITICAL)                         │
│  LLM Planner (prompts.yaml + gpt-oss-120b)            │
│       │                                               │
│       ▼ JSON plan                                     │
│  Auto-Responder ──SSH──▶ lab_server / lab_compromised │
│       │                  (OpenCode executes plan)      │
│       ▼                                               │
│  outputs/RUN_ID/slips/defender_alerts.ndjson          │
└──────────────────────────────────────────────────────┘
```

## Apéndice B: Flujo de una Corrida de Experimento

```
1. make up           → genera RUN_ID, crea árbol de outputs, levanta router+server+compromised
2. make defend       → levanta lab_slips_defender, provisiona llaves SSH
3. make benign       → inicia db_admin (agente de tráfico benigno)
4. make coder56 "…"  → inicia agente atacante con objetivo en lenguaje natural

Flujo interno (defender):
  router PCAP (30s) → SLIPS analiza → alerta HIGH/CRITICAL
  → forward_alerts.py → POST /plan (LLM planner)
  → JSON plan → auto_responder.py → SSH → OpenCode en lab_server/lab_compromised
  → commands ejecutados → exit_code + stdout/stderr logueados
  → timeline JSONL actualizado

5. make down         → detiene todo, elimina volúmenes (preserva outputs/)
```
