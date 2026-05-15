# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Simple Flask viewer for baseline oximetry data.

Single page with a night picker, summary stats, and an SpO2/HR chart.

Usage:
    python -m windows.viewer
    # then open http://localhost:5050
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template

from windows import db, stats


PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "o2_baseline.db"


app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "templates"),
    static_folder=str(PROJECT_ROOT / "static"),
)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/nights")
def api_nights():
    with db.connect(DB_PATH) as conn:
        nights = db.list_nights(conn)
    return jsonify({"nights": nights})


@app.route("/api/night/<night_date>")
def api_night(night_date: str):
    with db.connect(DB_PATH) as conn:
        readings = db.get_night_readings(conn, night_date)
    summary = stats.summarize(readings)
    return jsonify({
        "night_date": night_date,
        "readings": readings,
        "summary": summary,
    })


if __name__ == "__main__":
    db.init(DB_PATH)
    app.run(host="127.0.0.1", port=5050, debug=False)
