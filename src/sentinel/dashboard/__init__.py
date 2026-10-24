"""Project cockpit (WP8; ADR-0021): one simulated project under two policies on the same world,
written as one self-contained HTML page with the plan, the risk and the agent's decisions.

`world` builds the world and runs the policies, `assemble` turns the runs into the cockpit's
data, `explain` writes the explanations, `svg` draws the charts and `page` the HTML.
"""
