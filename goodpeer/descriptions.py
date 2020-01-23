goodpeers_small_desc = "Get a list of good enough peers to connect to, reversely sorted."

goodpeers_desc = \
"""
Get a list of good enough peers to connect to, reversely sorted.

{bias} can be set to "big" if you plan to make big payments or "small" if
you plan to make small payments. It will tweak the score computation
towards prefering small ppm fees (big) or small base fees (small). By
default no tweak is applied and they have the same weight.

{min_height} is useful to set because, by default, the fees stats will be
calculated upon all the active channels of a given node, which may have
changed its fees policy since.
"""
