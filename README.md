# ADSPA Academic Deadline and Study Planning Agent

A local-first planner for courses, coursework, exams, study materials, research projects, and study time. The dashboard brings deadlines, countdowns, workload risk, recovery suggestions, syllabus progress, and today's study plan together. It supports assignment workflows, revision and spaced repetition, structured research tracking, voice input, and optional reminders through browser notifications, Gmail, Telegram, and Google Calendar.

## Requirements and launch

- Python 3.10 or newer
- Visual Studio Code (optional)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run streamlit/streamlit_app.py
```

Open the local URL printed by Streamlit. The reminder service can run independently in another terminal:

```bash
source .venv/bin/activate
python src/agent.py reminder-service
```

Keep that process running for 15-minute deadline and study-session reminder checks and the daily briefing. The dashboard also starts a reminder scheduler while it is open. Both processes use a SQLite lease to avoid sending duplicate reminders. Stop the standalone service with Ctrl+C.

## Main features

- **Courses and materials:** keep course and semester details, upload PDF, PPTX, DOCX, TXT, Markdown, and CSV materials, search extracted source text, and extract numbered assignment questions. PDF text extraction does not perform OCR; scanned PDFs need OCR before upload. Source excerpts are distinguished from generated revision aids.
- **Deadlines and assignment workflows:** track assignments, quizzes, lab records, projects, continuous tests, and exams with date/time, estimate, difficulty, importance, consequence, completion, dependencies, custom reminders, checklists, lifecycle stages, final file, and submission confirmation.
- **Study planning:** create daily, weekly, and monthly plans within configured availability, class commitments, session lengths, breaks, remaining work, and exam revision needs. Mark work complete or missed and reschedule sessions into later available time.
- **Exam preparation:** record exams and formats, add syllabus units/topics, track coverage and weak areas, log quiz results, schedule spaced reviews, and configure countdown guidance for 14, 7, 3, and 1 days.
- **Risk and workload:** estimate deadline risk from remaining effort, difficulty, time available, competing work, and configured daily availability. The dashboard reports reasons, recovery actions, and deadline collisions. Priority weights are configurable.
- **Research tracking:** organize capstone/research projects, milestones, meetings, supervisor feedback, submissions, experiment states, configurations, dataset versions, checkpoints, metrics, and results.
- **Assistant and voice:** use academic commands without an API key, ask open-ended questions with optional AI setup, or dictate commands using browser speech recognition. Browser speech support depends on the browser and its speech services.
- **Reminders:** in-app and browser notifications are available locally. Gmail reminders are opt-in. Telegram reminders are optional. The scheduler requires the computer and one of the planner processes to remain running.

## Assistant setup (optional)

For open-ended AI chat, configure `OPENAI_API_KEY` in the server environment or `.streamlit/secrets.toml`, then restart Streamlit. Optionally set `OPENAI_MODEL`. API usage may incur charges; keep keys private. A local Ollama model can be used by setting `OLLAMA_MODEL` before launch. Local academic commands do not require either provider.

## Google Calendar and Gmail

1. In Google Cloud, create a project, enable Google Calendar API and Gmail API, configure the OAuth consent screen, and create an OAuth client with application type **Desktop app**.
2. Upload the OAuth client JSON in **Settings → Google Calendar and Gmail**. It is stored locally and excluded from Git.
3. Choose **Connect Google account** and complete Google's consent flow in the browser.
4. Choose **Sync coursework deadlines to Google Calendar** after adding or changing deadlines. Sync creates or updates events in the primary calendar.
5. To receive deadline email, enable Gmail reminders and set the recipient and advance notice in Settings. The planner sends each reminder interval once. The account grants send permission; the app does not read email.

Google's setup references: [Calendar Python quickstart](https://developers.google.com/workspace/calendar/api/quickstart/python) and [Gmail Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python).

## Telegram and browser notifications

Telegram is optional. Create a bot with Telegram's BotFather, obtain its bot token and chat ID, then enter them in Settings. Browser notifications require permission in the browser and work while the dashboard is open. In-app reminders are stored in the planner.

## Command line

```bash
python src/agent.py tasks
python src/agent.py add-task "Submit biology lab" --due 2026-11-03 --priority high --minutes 90 --category Biology
python src/agent.py plan
python src/agent.py note "Review lecture 5 before the quiz"
python src/agent.py mode focus
python src/agent.py focus-budget 180
python src/agent.py complete 1
```

## Data and migration

The planner stores structured records and settings in `data/academic_planner.db` (SQLite). On first launch, an existing `data/agent_data.json` is imported into SQLite. The JSON file is kept as a readable compatibility mirror. Back up both files while the app and reminder service are stopped. Uploaded files are stored under `data/course_materials/`; logs and local Google OAuth tokens remain on this computer and are excluded from Git.

`assignments_archive/` and selected files in `docs/` preserve the original ADSPA assignment work. The active dashboard and CLI are scoped to academic planning.
