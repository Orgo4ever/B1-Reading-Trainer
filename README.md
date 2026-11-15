# B1 Reading Trainer (Streamlit)

A personal, vocabulary-first preparation app for **Staatsexamen NT2 Programma I — Lezen (B1)**. Independent from DutchLearner and Woordkracht-1000.

**Exam target:** February/March 2027. **Built-in study content:** 143 curated A2+/B1 vocabulary items and 12 original reading lessons (48 questions). This is a starter curriculum, not a full archive of official exam materials.

## Features

- **Daily study plan** — six new words per day by default, plus scheduled reviews.
- **Spaced-repetition flashcards** — Again / Hard / Good / Easy with persisted due dates.
- **Typed recall** — checks the Dutch answer; a word is marked mastered only after successful spaced reviews and correct typing on two different days.
- **Reading lessons** — 12 original passages with four Dutch multiple-choice questions each, English explanations, and optional vocabulary glossaries.
- **Progress dashboard** — words introduced, conservative mastery, completed lessons, most recent accuracy and 14-day activity.
- **Exam prep** — a link to official online tests and a place to record your own mock scores. The app intentionally reserves the 2025 reading booklet as an unseen benchmark.
- **Backup & restore** — download progress JSON. Import custom vocabulary CSVs.
- **Persistent storage** — atomic local JSON for local use, **optional Google Sheets cloud sync** for cross-device use. Google Sheets is strongly recommended before deployment.

## Important source distinction

The user supplied the public NT2 Programma I **2023**, **2024**, and **2025** reading text booklets. The vocabulary and original reading exercises are informed by **2023–2024** themes; they are **not official exam questions**. The 2025 booklet is deliberately held out of lesson content. The submitted PDFs are text booklets, not separate official question/answer-key files. The field `source_years` reflects matching exact vocabulary forms in 2023 or 2024, while words marked “supporting” extend the vocabulary foundation.

The official 2025 reading booklet describes **6 texts, 35 multiple-choice questions, 110 minutes**. See <https://oefenexamensnt2.nl/> for actual practice exams.

## Quick start on a computer

Python 3.10+ recommended.

```bash
pip install -r requirements.txt
streamlit run app.py
```

This runs immediately without any cloud configuration; progress is saved in `data/progress.json` on that computer. Download JSON backups regularly. **Streamlit Community Cloud does not guarantee persistence of local files after restarts**, so don't use its local mode for long-term daily study.

## Put the app on GitHub + Streamlit Community Cloud

1. Make a new **private** GitHub repository (suggested name: `B1-Reading-Trainer`). Do not modify DutchLearner or Woordkracht-1000.
2. Upload the **contents** of this folder, including `app.py`, `core.py`, `storage.py`, `content/`, `requirements.txt`, and `.streamlit/config.toml` (but **not** your secrets).
3. At <https://share.streamlit.io>, create a new app with that GitHub repository, branch `main`, entrypoint `app.py`.
4. **Before using it regularly on your phone and computer, configure Google Sheets storage** in the app's Streamlit Cloud **Secrets** settings. See below. The app automatically uses cloud sync when both the service-account details and sheet ID are present.
5. Once secrets are saved, **reboot/redeploy** the app, check that the sidebar says `Google Sheets (cross-device)`, and test one flashcard on your computer and then your phone.

### Set up Google Sheets progress sync

The Google Sheet can be blank. Its first worksheet will be created automatically if needed.

1. Create a new Google spreadsheet named something like `B1 Reading Progress` and copy its spreadsheet ID from the URL.
2. Use a Google Cloud project with Google Sheets API enabled and a service account. You can reuse an existing service-account setup if you control it and prefer that, but **do not reuse any credentials by placing them in your GitHub repo**.
3. Share the spreadsheet with the service account's `client_email`, giving **Editor** access.
4. Open **Manage app → Settings → Secrets** in Streamlit Community Cloud.
5. Copy `.streamlit/secrets.toml.example` into the Secrets editor and replace placeholders with your credentials and sheet ID. Set a strong `APP_PASSCODE`; this app is intended for a single private learner, not a public class.
6. Save, restart and verify `Google Sheets (cross-device)` is visible. The `progress` worksheet stores a record by `USER_ID`. Progress is saved immediately after every review, lesson, mock or imported word.

**No Google Sheets configured?** The app uses local JSON. This is fine on a computer you control, but **not** a durable cross-device data strategy on Community Cloud.

## Adding content

`content/vocabulary.json` contains the built-in words. In the app's **Settings**, you can import a CSV with columns:

```csv
dutch,english,example,theme
ondanks,despite,Ondanks de regen gaan we fietsen.,connectors
```

`content/lessons.json` contains lesson text and multiple-choice questions. More lesson packs can be added later following the existing schema. The built-in passages are original and avoid reproducing long official passages verbatim.

## Checking the project

```bash
python -m pytest tests -q
python -m py_compile app.py core.py storage.py
```

## Recommended lesson rhythm

Spend around 10 minutes on vocabulary, 15 minutes on reading, and 5 minutes reviewing mistakes. Start without timing; add timed original sections once you can understand the texts reliably. Keep the 2025 official exam unseen until your first realistic full mock.
