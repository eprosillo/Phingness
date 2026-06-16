# Oura Data & Goals Tracker

Pull daily Oura Ring data, store it locally, and get goal-aware training recommendations.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and paste your Oura Personal Access Token
```

Get a token at https://cloud.ouraring.com/personal-access-tokens

## Usage

### CLI daily report
```bash
python report.py              # sync last 60 days, then print today's report
python report.py --no-sync    # use local DB only (no API call)
python report.py --goal endurance_base   # override goal for this run
python report.py --set-goal maintenance  # persist goal change
```

### Streamlit dashboard
```bash
streamlit run dashboard.py
```

## Goal profiles
Edit `config/goal_profiles.json` to tune thresholds.
Switch goals:
```bash
python report.py --set-goal weight_loss_fitness
```
Available: `weight_loss_fitness`, `endurance_base`, `maintenance`

## Project structure
```
oura/
  api.py        # Oura v2 REST calls
  db.py         # SQLite read/write
  ingest.py     # parse + upsert pipeline
goals/
  loader.py     # read/write goal profiles + current_goal.json
analysis/
  trends.py     # rolling HRV, RHR alert, sleep debt, recommendations
config/
  goal_profiles.json
  current_goal.json
report.py       # CLI entry point
dashboard.py    # Streamlit UI
oura_data.db    # created on first sync (gitignored)
```
