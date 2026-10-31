Assignment 4.2 — ADSPA Knowledge Representation and Adaptive API Integration

Files:
- Assignment_4_2_ADSPA_Knowledge_API.py — complete executable source
- Assignment_4_2_ADSPA_Knowledge_API.ipynb — notebook version
- Assignment_4_2_Adaptive_Verification_Log.txt — deterministic test output
- Assignment_4_2_ADSPA_Knowledge_API_Report.pdf — report and rubric mapping
- Assignment_4_2_ADSPA_Knowledge_API_Report.txt — plain-text report

Run deterministic verification:
  python Assignment_4_2_ADSPA_Knowledge_API.py

Fetch live weather from Open-Meteo:
  python Assignment_4_2_ADSPA_Knowledge_API.py --live

Custom location:
  python Assignment_4_2_ADSPA_Knowledge_API.py --live --latitude 13.0827 --longitude 80.2707

Live mode requires network access. The deterministic verification works offline and is not misrepresented as a live API fetch.
