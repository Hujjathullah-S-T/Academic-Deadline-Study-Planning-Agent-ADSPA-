# Assignment 3.1 — ADSPA Multi-Agent Coordination

## Files
- `Assignment_3_1_ADSPA_Negotiation.py`: runnable source code
- `Assignment_3_1_ADSPA_Negotiation.ipynb`: notebook execution wrapper and explanation
- `Assignment_3_1_Execution_Terminal_Timeline.txt`: full captured terminal timeline and rubric mapping
- `Assignment_3_1_Negotiation_Timeline.json`: structured message timeline
- `Assignment_3_1_ADSPA_Negotiation_Report.pdf`: formatted report

## Run
Requires Python 3.9+; standard library only.
```bash
python Assignment_3_1_ADSPA_Negotiation.py
```
For full payloads:
```bash
python Assignment_3_1_ADSPA_Negotiation.py --verbose
```

## Summary
Two independent ADSPA agents negotiate academic study support. The protocol is contract-net-inspired and contains a call for proposal, proposal, counter-proposal, revised proposal, acceptance, commit acknowledgement, and consensus confirmation. The simulated agreement is 120 minutes of support for 72 credits.

The final provider utility meets its configured 0.55 minimum, and the price is below the coordinator's 75-credit budget ceiling. The utility formulas are illustrative; no actual transaction occurs.
