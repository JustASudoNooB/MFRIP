# Run MFRIP — quick start

This is a small app that runs in your web browser. Setup takes about 5 minutes.
The only thing you need installed is a free tool called **Python**.

## 1. Install Python (skip if you already have it)

- Download from https://www.python.org/downloads/ and install it.
- On **Windows**, tick **"Add Python to PATH"** on the very first install screen (important).
- To check it worked, open a terminal and type `python --version` (on Mac, `python3 --version`). You should see 3.10 or higher.

## 2. Open a terminal **inside this folder**

- **Windows:** unzip this folder and open it. Click the address bar at the top, type `cmd`, and press Enter.
- **Mac:** unzip it, then right-click the folder and choose "New Terminal at Folder" (or open Terminal and drag the folder onto the window).

## 3. Install what it needs (one time)

```
pip install -r requirements.txt
```
(On Mac, if `pip` isn't found, use `pip3 install -r requirements.txt`.)

## 4. Start the app

```
python -m streamlit run app.py
```
(On Mac, use `python3 -m streamlit run app.py`.)

Your browser opens automatically at http://localhost:8501.

**The first time you open it,** it spends a minute or two downloading fund data
from the internet (you will see a progress note). After that it is instant. Keep
the terminal window open while you use the app; press Ctrl+C in it to stop.

## What to look at

Start on the **Start here** tab, and flip on the **Beginner mode** switch in the
left sidebar for plain-language explanations under everything. Then try:

- **Explore** — pick a fund; see its risk, rolling returns, behaviour in past crashes, and the **Monte Carlo goal planner** (probability fan of SIP outcomes).
- **Compare** — two funds head-to-head.
- **Portfolio Lab** — build portfolios and compare them.
- **Research** — audit an advisor's past picks, and scroll to the bottom for the **walk-forward validation** (does the ranking hold up out-of-sample).
- **Advisor** — enter funds you hold and get a health score and suggestions.

## Feedback I'm after

Anything: is it useful, is anything confusing, does any number look wrong, is
the wording clear, what would you add. Screenshots of anything odd are perfect.

## If something breaks

- *"python is not recognised"* — Python is not on PATH. On Windows, reinstall and tick "Add Python to PATH"; on Mac, use `python3`.
- *Can't download data* — check your internet. The data comes from a free public source that can occasionally lag; just try again.
- *Anything else* — screenshot it and send it back. That is exactly the kind of feedback that helps.

Full detail (the methods and the honest limitations) is in `README.md` and
`METHODOLOGY.md` in this same folder.
