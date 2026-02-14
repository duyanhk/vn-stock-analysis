# Financial Scraping UI

Flask web app that fetches Vietnamese stock financial data using **VNStock API** (primary) with **Vietstock web scraping** as fallback. Computes key ratios (ROE, ROIC, margins, growth) and visualizes them in an interactive dashboard.

## Data Sources

- **Primary**: VNStock API (fast, reliable, no browser required)
- **Fallback**: Vietstock web scraping (Selenium-based, used when VNStock fails)

## Setup

1. Create and activate a virtual environment (recommended).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. **Chrome** (optional): Required only when `ENABLE_SELENIUM=true` for Vietstock fallback. For cloud deployment with real API, leave Selenium disabled.

### Creating and activating a virtual environment on Windows

From the project root:

```bash
python -m venv .venv
```

#### PowerShell (with restricted execution policy)

If you see an error like:

> `.venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on this system`

you can temporarily relax the policy **only for the current PowerShell session**:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.venv\Scripts\Activate.ps1
```

#### Command Prompt (cmd.exe)

Alternatively, use Command Prompt, which does not enforce the same policy:

```bat
cd "D:\Dev Projects\Financial Scraping"
.venv\Scripts\activate.bat
```

## Run the app

From the project root:

```bash
python run.py
```

Then open `http://127.0.0.1:5000/` in your browser.

### Using sample data mode (skip scraping)

For UI debugging, you can serve data from a saved JSON snapshot instead of
running the Selenium scraper every time.

1. **Generate a sample once (live scrape)**  
   Run the app normally and complete one analysis so a sample file is written.

2. **Enable sample data via environment variable**

- **PowerShell**:

```powershell
$env:USE_SAMPLE_DATA = "True"
python run.py
```

- **Command Prompt (cmd.exe)**:

```bat
set USE_SAMPLE_DATA=True
python run.py
```

3. **Return to live scraping**

In a new terminal session, just run (same for PowerShell and cmd.exe):

```bash
python run.py
```

Or explicitly disable sample data:

- **PowerShell**:

```powershell
$env:USE_SAMPLE_DATA = "False"
python run.py
```

- **Command Prompt (cmd.exe)**:

```bat
set USE_SAMPLE_DATA=False
python run.py
```

## Usage

- Enter a Vietstock ticker (e.g. `HPG`) and click **Run analysis**.
- The app will:
  - Launch a headless Chrome session.
  - Scrape consolidated financial tables from Vietstock.
  - Compute ROE, ROIC, net profit margin, and YoY growth.
  - Plot ROE and ROIC over time.
  - Save a CSV into the `output/` folder and expose a download link.

## Stopping and deactivating

- To **stop** the app, press `Ctrl + C` in the terminal where `python run.py` is running.
- To **deactivate** the virtual environment:

```bash
deactivate
```

## Debug & operations

For rate limits, VNStock migration, data comparison, and troubleshooting, see **`debug/DEBUG.md`** (single combined guide). Debug and comparison scripts (e.g. `quick_compare.py`, `compare_data_sources.py`) live in the project root; run them from there.

## Deployment (Render)

**Required env vars on Render:**
- `FLASK_ENV=production`
- `USE_SAMPLE_DATA=true` (for demo; use `false` for live VNStock API)
- `ENABLE_SELENIUM=false`

**If you see "Network error" or 500:** Check Render Logs for the actual error. Ensure `USE_SAMPLE_DATA=true` for demo mode (no live API calls). On free tier, the service may sleep—first request after idle can take 30–60 seconds.

## Deployment (real API)

For cloud hosting (Render, Railway, etc.) where Chrome/Selenium is unavailable:

| Variable | Default | Purpose |
|----------|---------|---------|
| `FLASK_ENV` | — | Set `production` for ProductionConfig (DEBUG=False) |
| `USE_SAMPLE_DATA` | `false` | `true` = serve from sample JSON; `false` = use real APIs |
| `ENABLE_SELENIUM` | `false` | `true` = Vietstock Selenium fallback when VNStock fails |
| `USE_VNSTOCK_PRIMARY` | `true` | Use VNStock as primary data source |

**Cloud (no Chrome):** `ENABLE_SELENIUM=false` (default). VNStock only.

**Render (real API):** Set `USE_SAMPLE_DATA=false`. Build Command: `./build.sh` (or `pip install -r requirements.txt` + matplotlib font cache pre-build) to avoid 30s block on first request.

**Local / VPS (with Chrome):** `ENABLE_SELENIUM=true` to enable Vietstock fallback.

```bash
# Production with Gunicorn
FLASK_ENV=production gunicorn -w 4 -b 0.0.0.0:8000 wsgi:app
```

## Notes

- Scraping depends on Vietstock's HTML structure; if they change the site,
  the scraper may need updates.
- Selenium-based scraping can be slow; avoid hammering the site with many
  concurrent requests.

