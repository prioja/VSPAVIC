# VSPAVIC Web Experiment

VSPAVIC is now served as a Python-backed HTML application. The app has one main page with navigation between the experiment screens:

- Start
- Bid
- Result
- End

The frontend is plain HTML, CSS, and JavaScript in `web/`. The backend is the Python standard-library HTTP server in `main.py`, with JSON API routes for experiment state, bid submission, reset, and serialized session documentation.

## Requirements

- Python 3.10 or newer
- A modern web browser

No Python package installation is required for the web server.

## Run The Server

From this directory:

```bash
python3 main.py --port 8001
```

Then open:

```text
http://localhost:8001
```

If running from WSL and accessing from Windows, `http://localhost:8001` usually works because WSL forwards localhost ports to Windows. If it does not, bind to all interfaces:

```bash
python3 main.py --host 0.0.0.0 --port 8001
```

Then use either `http://localhost:8001` or the WSL IP address from:

```bash
hostname -I
```

## Access From A Different PC

To access the app from another PC on the same network, run the server so it listens on all network interfaces:

```bash
python3 main.py --host 0.0.0.0 --port 8001
```

Find the IP address of the machine running the server.

On Linux or WSL:

```bash
hostname -I
```

On Windows PowerShell:

```powershell
ipconfig
```

Look for the active Wi-Fi or Ethernet IPv4 address. From the other PC, open this URL in a browser:

```text
http://<server-ip-address>:8001
```

For example:

```text
http://192.168.1.25:8001
```

If the page does not load:

- Make sure both PCs are on the same network.
- Make sure the server is running with `--host 0.0.0.0`.
- Allow Python or port `8001` through the host machine's firewall.
- If the server is running inside WSL, use the Windows host IP for another PC on the network. WSL localhost forwarding is usually only for the Windows machine itself, not other computers.

## App Flow

1. Start page: enter Subject ID, Trial Condition, and Trial Number.
2. Bid page: enter a bid using the keypad and submit it.
3. Result page: shows whether the subject won, the subject bid, and robot bids.
4. End page: shows total payout and generated session documentation.

## API Routes

### `GET /api/state`

Returns the current experiment state.

### `GET /api/documentation`

Returns comprehensive serializable JSON documentation for the current session. The object includes:

- schema name and version
- generated timestamp
- application metadata
- session ID and timestamps
- participant ID
- trial condition and number
- auction values
- CSV output path
- event log

### `POST /api/start`

Starts a trial.

Example body:

```json
{
  "subjectId": "001",
  "trialCondition": "TH ~ Take Home",
  "trialNumber": "1"
}
```

### `POST /api/bid`

Submits a bid in cents.

Example body:

```json
{
  "cents": 354
}
```

### `POST /api/reset`

Clears the current in-memory session and starts a fresh session object.

## Data Output

Submitted bids are appended to CSV files in `data/`.

The generated filename format is:

```text
VSPAVIC<subject_id>_A_<condition><trial_number>.csv
```

For example:

```text
data/VSPAVIC001_A_TH1.csv
```

## Project Layout

```text
.
├── main.py
├── Robobidders.py
├── web/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── figs/
└── data/
```

## Notes

The legacy Kivy screen modules remain in the repository for reference, but `main.py` is now the runnable web server entry point.
