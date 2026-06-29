# Proyecto Delfín — Source Code

The full source code for this project lives at the **repository root**, organized as follows:

| Directory | Contents |
|---|---|
| `images/` | Docker container images: `lab_router`, `lab_server`, `lab_compromised`, `lab_slips_defender`, `lab_dashboard`, `config_app` |
| `images/slips_defender/defender/` | LLM Defender agent: planner, auto-responder, prompts |
| `scripts/defender_experiments/` | Experiment runners: brute force, exfiltration, injection |
| `scripts/benign_experiments/` | Benign traffic baseline agent |
| `scripts/coder56_experiments/` | Attacker LLM agent (coder56) experiments |
| `images/shared/` | Shared Python modules: OpenCode client, timeline, types |
| `tests/` | Unit and integration tests for dashboard API |
| `topologies/` | Network topology definitions |
| `guide/` | Architecture, agent, and experiment documentation |

This project is built on top of the **Trident** cyber-range framework developed at labsin-uncuyo:
https://github.com/labsin-uncuyo/Trident
