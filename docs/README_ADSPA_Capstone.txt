ADSPA Capstone — Assignment 5.2
================================
Included:
- ADSPA_Capstone.py — integrated runnable source
- ADSPA_Capstone.ipynb — Google Colab/Jupyter notebook
- ADSPA_Capstone_Runtime_Log.txt — captured deterministic execution
- ADSPA_Capstone_Architecture.png and .pdf — architecture schematic
- ADSPA_Capstone_3_Minute_Video_Script.txt — voice-over script/storyboard
- ADSPA_Capstone_Report.pdf — report and rubric mapping

Run locally:
  python ADSPA_Capstone.py

Optional live weather:
  python ADSPA_Capstone.py --live-weather --latitude 13.0827 --longitude 80.2707

The default run is deterministic and requires no third-party packages or internet access.
Live weather requires internet; on failure the program reports the failure and uses a clearly
identified fallback fixture.

Expected success markers:
INTEGRATED_MODULES_VERIFIED=True
AUTONOMOUS_TASK_COMPLETED=True
COOPERATIVE_AGREEMENT_REACHED=True
BDI_INTENTION_UPDATED=True
SECURITY_BREACH_BLOCKED=True
WORKER_PROCESSED_TASK=True
ALL_CAPSTONE_ASSERTIONS_PASSED=True

Limitations: classroom reference implementation, not production-certified. The cooperating peer
is simulated in-process rather than an actual remote socket. HMAC is symmetric and the demo key
must not be reused. Production requires managed keys, TLS/mTLS, durable replay tracking, persistence,
monitoring, and security testing.
