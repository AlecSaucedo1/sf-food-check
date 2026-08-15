# Inspection observations

SF Food Check keeps violation-level inspector observations separate from DataSF's published violation descriptions.

## Why this is a separate enrichment layer

The current DataSF inspection feed provides the inspection outcome and violation findings, but the full report narrative is served through the official MyHealthDepartment report experience. Automated server-side requests to the San Francisco MyHealthDepartment portal currently return HTTP 403, including requests from hosted CI with normal browser headers. The application therefore does not scrape, invent, or infer report observations.

Only observations copied from a verified official inspection report should be imported.

## Import format

Use `data/observations_import_template.csv` or JSON records with these fields:

- `permit_number` and `inspection_date`, or an explicit `inspection_id`
- optional `inspection_type` when more than one inspection exists on the same date
- `violation_code` when the observation can be tied to a cited code
- `observation_text` — verbatim inspector observation
- optional `corrective_action` — verbatim related corrective action
- `report_url` — required official report URL
- optional `source_label`
- optional `sequence_number`

Import with:

```bash
python scripts/import_observations.py data/observations_import_template.csv
```

For the production Render disk:

```bash
DATABASE_PATH=/var/data/inspections.db python scripts/import_observations.py /path/to/verified_observations.csv
```

## Matching policy

The application matches report observations to violations by normalized health-code tokens. A single report code can match one code inside a grouped DataSF finding. If a report observation cannot be matched confidently, it remains visible under **Other inspector observations** instead of being assigned to a violation by guesswork.

## Observation severity

The observation severity score is an independent SF Food Check interpretation of the specific condition described in the report. It is separate from:

- the official SFDPH inspection outcome;
- the published violation description;
- the violation-level Foodborne Illness Risk Index.

The model prioritizes direct contamination pathways and concrete observed conditions. Examples include sewage exposure, symptomatic food workers, contamination of food or food-contact surfaces, active vermin, unsafe temperature control, handwashing failures, sanitation failures, structural conditions, and administrative findings.

Every displayed observation includes:

- the verbatim official observation;
- a 0–100 observation severity score and band;
- confidence;
- a short rationale;
- corrective action when imported;
- official-report provenance.

The score is not an official SFDPH score and is not a probability that a restaurant will cause illness.
