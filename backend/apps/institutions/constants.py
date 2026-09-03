"""Fixed rubrics for Institution DNA.

Which level a campus sits at is data (a column on `Institution`); what each
level *means* is the framework's own definition, so it lives here as a
constant. Same split `apps.scoring.constants` makes between the eight pillar
keys (a closed set the CRI framework defines) and their weights (configurable
rows).
"""

#: Plain-language description of each digital maturity level, shown beneath
#: the level itself on the Systems & IT tab.
DIGITAL_MATURITY_DESCRIPTIONS = {
    1: 'Processes are predominantly paper-based, with little digital record-keeping.',
    2: 'Most processes have some digital touchpoints but lack integration and automation.',
    3: 'Core systems are integrated and share data, and routine processes are automated.',
    4: 'Decisions are driven by data from connected systems, with reporting largely automated.',
    5: 'AI is embedded in academic and administrative processes under a governed institutional policy.',
}
