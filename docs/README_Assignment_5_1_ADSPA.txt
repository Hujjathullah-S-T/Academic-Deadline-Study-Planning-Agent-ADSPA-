Assignment 5.1 — ADSPA Authentication and Host Integrity
===========================================================

Files
-----
- Assignment_5_1_ADSPA_Authentication.py : standard-library implementation
- Assignment_5_1_ADSPA_Authentication.ipynb : Google Colab/Jupyter notebook
- Assignment_5_1_Runtime_Verification_Log.txt : captured execution output
- Assignment_5_1_ADSPA_Authentication_Report.pdf : report mapped to the rubric

Run locally
-----------
python Assignment_5_1_ADSPA_Authentication.py

Run in Google Colab
-------------------
Upload the .py and .ipynb files, open the notebook, and Run all. Keep the .py file
in the notebook's working directory.

Expected final lines
--------------------
TAMPERED_PAYLOAD_BLOCKED=True
UNTRUSTED_HOST_BLOCKED=True
DISALLOWED_COMMAND_BLOCKED=True
REPLAY_BLOCKED=True
REJECTED_REQUESTS_DID_NOT_CHANGE_STATE=True
ALL_SECURITY_ASSERTIONS_PASSED=True

Security note
-------------
This is a classroom demonstration. HMAC-SHA256 is a symmetric message
authentication code, not a public-key digital signature. The embedded key is
for demonstration only; production deployments must use managed secrets or a
proper public-key signature scheme, secure transport, key rotation, and robust
replay protection.
