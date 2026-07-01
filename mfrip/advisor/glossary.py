"""Plain-language explanations so a complete beginner understands what each score
and metric means, why it matters, and how to read it, written to sound like a
sharp friend explaining over coffee rather than a textbook.
"""
from __future__ import annotations

# the six things we score a portfolio on
PARAM_HELP = {
    "Diversification": "When the market drops, do all your funds dive together, or do some hold their "
                       "ground? If they all sink at once, they aren't really protecting each other. The more "
                       "they move on their own, the safer you are.",
    "Risk match": "Is your portfolio as bold (or as cautious) as you actually are? This checks whether its "
                  "real-world riskiness lines up with the risk you told us you're comfortable taking.",
    "Consistency": "Did this deliver steadily, or only in a few lucky stretches? We count how often it stayed "
                   "positive across many overlapping one-year periods. Fewer nasty surprises, higher score.",
    "Downside protection": "When things went wrong, how bad did it get? This looks at the deepest fall from a "
                           "high point. Smaller, more bearable drops score better.",
    "Concentration": "Are you betting too much on a single fund? If one holding carries most of your money, one "
                     "bad call really stings. Spreading your money sensibly scores higher.",
    "Liquidity": "If you needed your money back, could you get it quickly? Open-ended mutual funds score high "
                 "here. You can usually pull your money out within a day or two.",
}

# metrics
METRIC_HELP = {
    "CAGR": "The smooth, steady yearly growth rate your money actually compounded at, with all the ups and "
            "downs ironed flat. Think of it as the interest rate that would have got you to the same place.",
    "Volatility": "How much the value jumps around month to month. High volatility is a rollercoaster, bigger "
                  "highs and scarier lows. Low volatility is a gentler ride.",
    "Sharpe": "How much return you earned for the bumpiness you put up with. Higher is better. Above 1 is good, "
              "above 2 is excellent.",
    "Sortino": "Sharpe's smarter cousin. It counts only the downward bumps, the ones that keep you up at night, "
               "and ignores the pleasant surprises. Higher is better.",
    "Max drawdown": "The worst peak-to-bottom fall it ever suffered. A drawdown of 30% means that at some point "
                    "it lost nearly a third of its value before clawing back. It's the gut-check: could you "
                    "have held on through that?",
    "Alpha": "The extra return a fund earned beyond what the market handed it for free. Positive alpha hints at "
             "skill, but it's always measured against a benchmark, so the benchmark you pick matters.",
    "Beta": "How hard a fund swings compared with the market. A beta of 1 moves in step with it; above 1 is "
            "jumpier than the market, below 1 is calmer.",
    "Correlation": "Whether two funds move as a pair. 1.0 means they're practically twins; 0 means they go "
                   "their own way. Holding funds with low correlation is what real diversification looks like.",
}


def scoring_intro() -> list[str]:
    """A short 'how we judge your portfolio' explainer, in plain language."""
    return [
        "We don't try to guess which fund will win, because honestly, nobody can. What we *can* do is check "
        "whether your portfolio is built well and genuinely fits you. We look at six things:",
        "**Diversification**: when one fund falls, do the others fall with it?",
        "**Risk match**: is it as bold, or as cautious, as you are?",
        "**Consistency**: has it delivered steadily, or just caught a lucky run?",
        "**Downside protection**: how hard does it fall when markets turn?",
        "**Concentration**: is your money spread, or riding on one bet?",
        "**Liquidity**: can you get your cash out the moment you need it?",
        "Each one is scored out of 100 from your funds' real history, and we roll them into a single Health Score.",
    ]


# onboarding: what a first-time investor can do, and where
TASK_GUIDE = [
    ("🔍", "Look up a single fund", "Explore a fund",
     "Pull up any mutual fund and see the whole story: its returns, how wild the ride was, the full range of "
     "outcomes across every holding period, how much of the market's ups and downs it caught, and how it held "
     "up when markets crashed.",
     "Start here if you already have a fund in mind."),
    ("🩺", "Check a portfolio you own", "Advisor",
     "Tell us what you already hold, and we'll give it a proper health check: does it suit you, where's the "
     "hidden risk, and what would you change to make it stronger.",
     "Best if you already invest and want a second opinion."),
    ("✨", "Get a recommendation", "Advisor",
     "Answer a few quick questions about yourself and we'll build a portfolio that fits your situation, then "
     "show you exactly why we picked what we picked.",
     "Best if you're just getting started."),
    ("⚖️", "Build and compare portfolios", "Portfolio Lab",
     "Mix funds into a few different portfolios and put them side by side: growth, risk, and whether the funds "
     "actually complement each other or just double up.",
     "Best for testing ideas before you commit real money."),
    ("📄", "Audit advice or make a report", "Research",
     "See whether an advisor's past picks actually beat a fair benchmark, or generate a clean research report "
     "you can save and share.",
     "Best for doing your homework."),
]

# how MFRIP reasons: the four things to keep apart
TRUST_LAYERS = [
    ("📊 Evidence", "Hard numbers, measured straight from real price history: returns, drawdowns, how funds "
     "move together. These are facts, not opinions."),
    ("🧭 Interpretation", "The plain-English conclusions we draw from those facts, like 'this is concentrated' "
     "or 'this suits a cautious investor'. Sensible reasoning, but still judgement, not certainty."),
    ("📐 Assumptions", "Whenever we look ahead (projecting a goal, say), we show a whole range of outcomes "
     "instead of one confident number, because the future simply isn't ours to know."),
    ("⚠️ Limitations", "The things we genuinely can't see or promise. We put them in plain sight so you can "
     "weigh the analysis with your eyes open."),
]

# the honest limits of the tool and its data
LIMITATIONS = [
    "We don't predict returns. Nothing here will tell you which fund is about to take off, because that isn't "
    "knowable, and any app claiming otherwise is worth walking away from. What we do is judge whether a "
    "portfolio is built well and suits you.",
    "We can't see a fund's expense ratio or its size, because our free data source doesn't carry them. So our "
    "ranking leans on what the price history can tell us, and we're upfront about adjusting the scoring for it.",
    "When we say two funds 'overlap', we mean they tend to move together, not that they literally hold the same "
    "stocks. We can't peer inside the funds, so we read the shadow they cast, not the holdings themselves.",
    "Our data comes from a free, public source. Once in a while it lags a day or hands back an incomplete list.",
    "Everything here is for learning, not financial advice. The past is context, never a promise.",
]

PHILOSOPHY = (
    "MFRIP isn't a crystal ball, and it won't pretend to be one. It can't tell you which fund will go up. "
    "What it can do is look hard at what you hold (or what you're tempted to buy), tell you whether it's built "
    "sensibly and fits your life, and show you every step of its reasoning, so you can trust the answer because "
    "you can see exactly how we got there."
)
