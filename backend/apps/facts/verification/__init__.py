"""Shared fact verification and safe automation (see engine.py for the pipeline, policy.py for automation).

Deterministic checks (normalize, grounding, validators, derived, scope, conflicts) never involve the AI. AI
output appears only as the extracted value itself, its extraction confidence, and labelled AI-assisted notes --
none of which can confirm a fact or resolve a conflict.
"""
