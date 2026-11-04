Evening calendar scan, {{WEEKDAY}} {{TODAY}}. Do not message the athlete unless something new is scheduled.

1. `get_plan` from today for the next 14 days.
2. Find events that need preparation: races (race flag or race category), fitness tests (ramp test,
   FTP test, submaximal fatigue test, time trial, anything named "test"), and long or key sessions
   that need fuelling or logistics (over 3 h, or group rides with a start time).
3. `list_reminders` to see what already exists.
4. For each such event create reminders with `add_reminder`, always with a `dedupe_key` of the form
   `event:<date>:<short-name>:<slot>`:
   - Tests: the evening before at 19:30 (rest, sleep, carbs at dinner, trainer and power meter
     charged/calibrated); the morning of at 07:00 (warm-up, fuelling, how the test is paced).
   - Races: 3 days before at 19:00 (taper, check bike, entry/licence); the evening before at 19:30
     (kit, nutrition, bottles, arrival time); the morning of at 06:30 (breakfast timing, hydrate,
     weather).
   - Long/key sessions: the evening before at 19:30 (route, fuel, bottles).
   Skip any slot already in the past. Make each reminder self-contained and specific to the event.
5. If you created any reminder, reply with a short list of what you scheduled. If nothing new was
   needed, reply with exactly NOTHING_TO_REPORT and nothing else.
