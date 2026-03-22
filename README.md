# WHOOP Data Exporter

A Python script that exports your [WHOOP](https://www.whoop.com/) health and fitness data to CSV files using the official [WHOOP Developer API](https://developer.whoop.com/api).

## What it does

The script authenticates with your WHOOP account via OAuth 2.0, then downloads and exports the following data to CSV files:

| Data | Output file | Description |
|------|------------|-------------|
| Sleep | `sleep.csv` | Sleep records with duration, stages, and quality scores |
| Recovery | `recovery.csv` | Daily recovery scores, HRV, resting heart rate |
| Workouts | `workouts.csv` | Workout activities with strain, heart rate zones, calories |
| Cycles | `cycles.csv` | Physiological cycles with strain and recovery data |

All nested JSON fields are flattened into individual columns with snake_case names (e.g. `score.recovery_score` → `score_recovery_score`).

## Prerequisites

- Python 3.9+
- A WHOOP account with an active membership
- A registered app on the [WHOOP Developer Portal](https://developer.whoop.com/) with the redirect URI set to `http://localhost:3000/callback`

## Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/<your-username>/whoop-data-exporter.git
   cd whoop-data-exporter
   ```

2. **Install dependencies:**

   ```bash
   pip3 install requests pandas python-dotenv
   ```

3. **Configure credentials:**

   Copy the example environment file and fill in your WHOOP app credentials:

   ```bash
   cp .env.example whoop.env
   ```

   Open `whoop.env` and replace the placeholder values with your real Client ID and Client Secret from the WHOOP Developer Portal.

## Usage

Run the script:

```bash
python3 export_whoop.py
```

The script will:

1. Open your browser to the WHOOP authorization page
2. Start a temporary local server on `http://localhost:3000/callback` to capture the OAuth callback
3. Exchange the authorization code for an access token
4. Automatically detect your earliest WHOOP record and fetch all data from that date through today
5. Save each dataset as a CSV file in the current directory

Progress is printed to the console as data is fetched.

## Features

- **OAuth 2.0 Authorization Code flow** — secure browser-based login, no password handling
- **Automatic pagination** — fetches all records across multiple pages
- **Rate limit handling** — exponential backoff with automatic retry on `429` and `5xx` responses
- **Automatic start date detection** — finds your earliest logged record so no data is missed
- **Flat CSV output** — nested JSON structures are flattened into readable column names

## API Reference

This script uses the [WHOOP Developer API v2](https://developer.whoop.com/api):

- `GET /v2/activity/sleep`
- `GET /v2/recovery`
- `GET /v2/activity/workout`
- `GET /v2/cycle`

## License

MIT
