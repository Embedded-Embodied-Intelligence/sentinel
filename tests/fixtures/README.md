# Test fixtures

`tiny.sm` — hand-made PSPLIB-format instance (3 real activities, 1 renewable resource,
capacity 3). Known values: LB0 = 7 (path 0→1→3→4), optimal makespan = 7
(activity 1 at 0–3, activity 3 at 3–7, activity 2 at 3–5; activities 1 and 2 cannot overlap
because 2 + 2 > 3). Activity ids are 0-based as returned by `psplib`.
