# Architecture

```text
Streamlit dashboard / CLI / VS Code
              |
              v
       Streamlit dashboard
         |       |       |
         |       |       +--> Browser voice component
         |       +----------> src/google_workspace.py (optional Google APIs)
         +------------------> src/agent.py (CLI and local data services)
                                |      |      |
                                |      |      +--> src/modules.py (risk, schedule, progress)
                                |      +---------> data/agent_data.json and activity log
                                +----------------> Tasks linked to courses by course_id
```

The active app focuses on course records, assignments, projects, study materials, deadlines, study plans, study notes, academic progress, and study-focused chat. Course metadata and material references are stored in `data/agent_data.json`; uploaded materials live in `data/course_materials/`. Assignments and projects are planner tasks linked with a `course_id`, so deadlines flow into plans and progress. The planner and schedule estimates are deterministic and based on saved tasks, estimates, and manually entered class commitments. Calendar export creates an `.ics` file for manual import; optional Google sync and Gmail reminders use `src/google_workspace.py`.

The original assignment scripts and notebooks remain in `assignments_archive/` as historical project material.
