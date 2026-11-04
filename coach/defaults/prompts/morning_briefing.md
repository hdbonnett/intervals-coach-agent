Morning readiness check for today, {{WEEKDAY}} {{TODAY}}.

1. `get_orientation`, then `get_wellness` for the last 28 days, `get_fitness`, `get_plan` from
   today for 7 days, and `list_activities` for the last 3 days.
2. {{ATTEMPT_NOTE}}
3. Write the brief for Telegram, in this order and under about 180 words:

   - First line: the status emoji and word (🟢 Green / 🟡 Amber / 🔴 Red) and a one-line reason.
   - **Sleep:** last night's duration and score/quality as returned, and how it compares with the
     last few nights.
   - **HRV / resting HR:** today's values and where they sit in the recent run.
   - **Load:** fitness, fatigue and form as returned by `get_fitness`, in one line.
   - **Today:** the planned session (name, duration, load) and your call: as planned, or exactly
     how to adjust. If it's an outdoor day and the plan carries weather, mention heat or wind if it
     matters for pacing or hydration.
   - **Coming up:** any test, race or key session in the next 7 days, with the date.

   If a field is missing, say so in a few words rather than guessing.
