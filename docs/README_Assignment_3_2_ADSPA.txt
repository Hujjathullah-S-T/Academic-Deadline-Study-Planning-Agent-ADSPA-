# Assignment 3.2 — ADSPA Self-Interested Utility Optimization

## Files
- `Assignment_3_2_ADSPA_Utility_Optimization.py`: runnable implementation
- `Assignment_3_2_ADSPA_Utility_Optimization.ipynb`: notebook runner and explanation
- `Assignment_3_2_Execution_Terminal_Log.txt`: captured execution output and rubric mapping
- `Assignment_3_2_Optimization_Results.json`: structured scores, feasibility checks and selected offer
- `Assignment_3_2_ADSPA_Utility_Optimization_Report.pdf`: formatted report

## Run
Requires Python 3.9+ and uses only the standard library.
```bash
python Assignment_3_2_ADSPA_Utility_Optimization.py
```
For rejection reasons for each infeasible candidate:
```bash
python Assignment_3_2_ADSPA_Utility_Optimization.py --verbose
```

## Model
Utility = 0.30*quality + 0.20*delivery_score + 0.20*convenience + 0.30*study_value - 0.04*total_price.
The agent selects the global maximum utility among feasible offers only. The credits and offers are simulated.
