from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import argparse
import csv
import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

from Robobidders import roboModel


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
DATA_ROOT = ROOT / "data"


class ExperimentState:
    def __init__(self):
        self.session_id = str(uuid4())
        self.created_at = utc_now()
        self.started_at = None
        self.completed_at = None
        self.subject_id = ""
        self.trial_condition = ""
        self.trial_number = ""
        self.subject_bid = 0.0
        self.robot_bids = []
        self.did_win = False
        self.total_payout = 0.0
        self.auction_file = ""
        self.events = []

    def as_dict(self):
        return {
            "sessionId": self.session_id,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "subjectId": self.subject_id,
            "trialCondition": self.trial_condition,
            "trialNumber": self.trial_number,
            "subjectBid": self.subject_bid,
            "robotBids": self.robot_bids,
            "didWin": self.did_win,
            "totalPayout": self.total_payout,
            "auctionFile": self.auction_file,
        }

    def documentation(self):
        return {
            "schema": {
                "name": "vspavic-session-documentation",
                "version": "1.0.0",
            },
            "generatedAt": utc_now(),
            "application": {
                "name": "VSPAVIC Experiment",
                "runtime": "python-http-server-html",
            },
            "session": {
                "id": self.session_id,
                "createdAt": self.created_at,
                "startedAt": self.started_at,
                "completedAt": self.completed_at,
            },
            "participant": {
                "subjectId": self.subject_id,
            },
            "trial": {
                "condition": self.trial_condition,
                "number": self.trial_number,
            },
            "auction": {
                "subjectBid": self.subject_bid,
                "robotBids": self.robot_bids,
                "winningBid": self.subject_bid if self.did_win else None,
                "didSubjectWin": self.did_win,
                "totalPayout": self.total_payout,
                "csvFile": self.auction_file,
            },
            "events": self.events,
        }

    def record_event(self, event_type, payload=None):
        self.events.append(
            {
                "type": event_type,
                "timestamp": utc_now(),
                "payload": payload or {},
            }
        )


def utc_now():
    return datetime.now(timezone.utc).isoformat()


STATE = ExperimentState()
ROBOT_MODEL = roboModel(0.4395073979128712, 0.05735650555767768, 2)


class VSPAVICHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_ROOT, **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/state":
            self.send_json(STATE.as_dict())
            return

        if path == "/api/documentation":
            self.send_json(STATE.documentation())
            return

        if path == "/" or path == "/index.html":
            self.path = "/index.html"
        return super().do_GET()

    def translate_path(self, path):
        parsed_path = urlparse(path).path
        if parsed_path.startswith("/figs/"):
            asset_name = parsed_path.removeprefix("/figs/")
            return str(ROOT / "figs" / asset_name)
        return super().translate_path(path)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if path == "/api/start":
                self.handle_start(payload)
            elif path == "/api/bid":
                self.handle_bid(payload)
            elif path == "/api/reset":
                self.handle_reset()
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def handle_start(self, payload):
        subject_id = str(payload.get("subjectId", "")).strip()
        trial_condition = str(payload.get("trialCondition", "")).strip()
        trial_number = str(payload.get("trialNumber", "")).strip()

        if not subject_id or not trial_condition or not trial_number:
            raise ValueError("Subject ID, trial condition, and trial number are required.")

        STATE.subject_id = subject_id
        STATE.trial_condition = trial_condition
        STATE.trial_number = trial_number
        STATE.subject_bid = 0.0
        STATE.robot_bids = []
        STATE.did_win = False
        STATE.auction_file = str(Path("data") / self.auction_filename())
        STATE.started_at = utc_now()
        STATE.completed_at = None
        STATE.record_event(
            "trial_started",
            {
                "subjectId": subject_id,
                "trialCondition": trial_condition,
                "trialNumber": trial_number,
            },
        )

        self.send_json(STATE.as_dict())

    def handle_bid(self, payload):
        cents = int(payload.get("cents", 0))
        if cents <= 0:
            raise ValueError("Bid must be greater than $0.00.")

        STATE.subject_bid = round(cents / 100, 2)
        STATE.robot_bids = [float(max(0.01, bid)) for bid in ROBOT_MODEL.get_bids()]
        STATE.did_win = STATE.subject_bid <= min(STATE.robot_bids)
        if STATE.did_win:
            STATE.total_payout = round(STATE.total_payout + STATE.subject_bid, 2)
        STATE.completed_at = utc_now()
        STATE.record_event(
            "bid_submitted",
            {
                "subjectBid": STATE.subject_bid,
                "robotBids": STATE.robot_bids,
                "didSubjectWin": STATE.did_win,
                "totalPayout": STATE.total_payout,
            },
        )

        self.write_auction_row()
        self.send_json(STATE.as_dict())

    def handle_reset(self):
        global STATE
        STATE = ExperimentState()
        self.send_json(STATE.as_dict())

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_auction_row(self):
        DATA_ROOT.mkdir(exist_ok=True)
        filename = self.auction_filename()
        STATE.auction_file = str(Path("data") / filename)
        path = DATA_ROOT / filename
        is_new = not path.exists()

        with path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if is_new:
                writer.writerow(
                    [
                        "subject_id",
                        "trial_condition",
                        "trial_number",
                        "subject_bid",
                        "robot_bid_1",
                        "robot_bid_2",
                        "did_win",
                        "total_payout",
                    ]
                )
            writer.writerow(
                [
                    STATE.subject_id,
                    STATE.trial_condition,
                    STATE.trial_number,
                    f"{STATE.subject_bid:.2f}",
                    f"{STATE.robot_bids[0]:.2f}",
                    f"{STATE.robot_bids[1]:.2f}",
                    STATE.did_win,
                    f"{STATE.total_payout:.2f}",
                ]
            )

    def auction_filename(self):
        condition = STATE.trial_condition.split("~", 1)[0].strip().replace(" ", "")
        return f"VSPAVIC{STATE.subject_id}_A_{condition}{STATE.trial_number}.csv"


def run(host="127.0.0.1", port=8000):
    server = ThreadingHTTPServer((host, port), VSPAVICHandler)
    print(f"VSPAVIC web app running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the VSPAVIC HTML experiment server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run(args.host, args.port)
