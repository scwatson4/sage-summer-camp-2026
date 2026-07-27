"""Ignition-risk scoring + responder notification cards (D5, plan F4).

Transparent weighted score — no black box, every factor's value and source
shown on the card (the plan's explicit model-shape decision: with ~zero
labeled ignition outcomes, a literature-weighted linear score beats an
untrainable classifier). Weights are the m1-results v0.1 placeholders;
tune at camp, keep the breakdown visible forever.
"""
from .score import RiskFactors, score  # noqa: F401
from .card import build_card, render_markdown, send_slack  # noqa: F401
