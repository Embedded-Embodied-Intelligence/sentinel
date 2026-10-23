"""Interpretation layer (WP6b; spec section 10): the LLM's three roles around the decision layer.

Role 1 (`events`, `messages`): team messages become events, validated and applied to the
observation by code. Role 2 (`actions`, `describe`): proposals in a fixed JSON grammar,
compiled into candidates that Sentinel's rollouts evaluate and its rule chooses among. Role 3
(`explain`): explanations of a `DecisionRecord`, checked for faithfulness. LLM output enters the
decision layer only as validated, compiled objects; no rollout or simulation path imports this
package (a test enforces it).
"""
