# Healthcare Prior Authorization Chatbot

A conversational AI assistant powered by **Claude** that integrates live healthcare
data through Claude Code's plugin infrastructure — no hardcoded URLs, no manual
API keys for data sources.

---

## Architecture

```
pa_chatbot.py
    │
    ├── load_plugin_mcp_servers()
    │       Reads ~/.claude/plugins/installed_plugins.json at startup
    │       Discovers MCP server URLs from installed plugin registry
    │       Exits with error if registry missing or no servers found
    │
    ├── _check_mcp_servers()
    │       HEAD-probes each discovered server before chat starts
    │       Exits with error if any server is unreachable
    │
    └── client.beta.messages.create(mcp_servers=[...])
            ├── NPI Registry MCP    → provider lookup / credential verification
            ├── ICD-10 Codes MCP    → diagnosis codes, validation, hierarchies
            └── CMS Coverage MCP    → Medicare NCD/LCD coverage policies
```

> **Policy:** MCP server URLs are never hardcoded. See [CLAUDE.md](CLAUDE.md).

---

## Required Plugins

Install both plugins in Claude Code before running the chatbot:

```bash
claude plugin install healthcare/fhir-developer
claude plugin install healthcare/prior-auth-review
```

| Plugin | MCP Servers Provided |
|--------|----------------------|
| `healthcare/fhir-developer` | NPI Registry, ICD-10 Codes, CMS Coverage |
| `healthcare/prior-auth-review` | Prior auth skill, sample PA data |

---

## Setup

```bash
# 1. Clone / navigate to project
cd claude_priorauthskill

# 2. Activate your Python environment
conda activate payerai-gpt

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API key
cp .env.example .env          # then add your ANTHROPIC_API_KEY

# 5. Run
python pa_chatbot.py
```

### Expected startup output

```
Loading MCP servers from Claude Code plugin registry...
  Found 3 MCP server(s):
    • [fhir-developer@healthcare] NPI Registry → https://mcp.deepsense.ai/npi_registry/mcp
    • [fhir-developer@healthcare] ICD10 Codes  → https://mcp.deepsense.ai/icd10_codes/mcp
    • [fhir-developer@healthcare] CMS Coverage → https://mcp.deepsense.ai/cms_coverage/mcp

Checking MCP server availability...
  ✅ npi_registry
  ✅ icd10_codes
  ✅ cms_coverage
```

---

## Use Case × Plugin Workflow Reference

| # | Use Case | Plugin Source | MCP Connectors Called | Tools Invoked | Skill Layer |
|---|----------|--------------|----------------------|---------------|-------------|
| — | **Plugin Verification** | `fhir-developer` + `prior-auth-review` | NPI Registry, ICD-10 Codes, CMS Coverage | `npi_lookup_provider` · `icd10_validate` · `cms_search_ncds` | None — raw connector test |
| 1a | **Differential Dx — symptom mapping** | `fhir-developer` | ICD-10 Codes | `icd10_search_codes` · `icd10_get_details` | `prior-auth-review` PA guidance |
| 1b | **Differential Dx — accuracy verification** | `fhir-developer` | ICD-10 Codes · CMS Coverage | `icd10_validate` · `cms_search_lcds` | `prior-auth-review` PA guidance |
| 2a | **Drug interaction — flag & code** | `fhir-developer` | ICD-10 Codes | `icd10_search_codes` · `icd10_get_details` | Claude clinical training |
| 2b | **Drug interaction — code validation** | `fhir-developer` | ICD-10 Codes | `icd10_validate` | `prior-auth-review` PA guidance |
| 3a | **Dosage — pediatric** | `fhir-developer` | ICD-10 Codes · CMS Coverage | `icd10_search_codes` · `cms_search_ncds` | Claude clinical training |
| 3b | **Dosage — elderly / Beers Criteria** | `fhir-developer` | ICD-10 Codes · CMS Coverage | `icd10_validate` · `cms_search_lcds` | Claude clinical training + `prior-auth-review` |
| 3c | **Dosage — renal impairment** | `fhir-developer` | ICD-10 Codes · CMS Coverage | `icd10_validate` · `cms_search_all` | Claude clinical training + `prior-auth-review` |
| 4 | **Full PA walkthrough** | `fhir-developer` + `prior-auth-review` | **All three** — NPI · ICD-10 · CMS | `npi_lookup_provider` · `icd10_validate` · `cms_search_lcds` / `cms_lcd_details` | `prior-auth-review` full skill |

### Workflow Legend

| Term | Meaning |
|------|---------|
| **MCP Connector** | Live data source called by Claude via the Anthropic remote MCP API |
| **Plugin Source** | Which installed Claude Code plugin provides the MCP server endpoint |
| **Skill Layer** | Domain intelligence applied on top of raw MCP data — either the `prior-auth-review` skill's PA workflow logic or Claude's built-in clinical training |
| **Tools Invoked** | Specific MCP tool functions Claude calls within the connector |

### Per-Use-Case Flow

```
Use Case 1 (Differential Dx)
  User message → Claude → icd10_search_codes (ICD-10 MCP)
                        → icd10_get_details  (ICD-10 MCP)
                        → [if verification] icd10_validate + cms_search_lcds
                        → Claude synthesizes with PA skill guidance → Answer

Use Case 2 (Drug Interactions)
  User message → Claude reasons with clinical training
                        → icd10_search_codes  (ICD-10 MCP)  ← adverse event codes
                        → icd10_validate       (ICD-10 MCP)  ← billability check
                        → Answer with PA auth guidance

Use Case 3 (Dosage by Profile)
  User message → Claude reasons with clinical training
                        → icd10_validate       (ICD-10 MCP)
                        → cms_search_lcds      (CMS Coverage MCP)  ← coverage criteria
                        → Answer with dosing + PA context

Use Case 4 (Full PA Walkthrough) ← exercises ALL three MCPs
  User message → Claude → npi_lookup_provider  (NPI Registry MCP)
                        → icd10_validate        (ICD-10 MCP)
                        → cms_search_lcds       (CMS Coverage MCP)
                        → cms_lcd_details       (CMS Coverage MCP)
                        → prior-auth-review skill applies PA rubric → Decision
```

---

## Plugin Verification Queries

Run these immediately after startup to confirm all three MCP connectors are
working correctly. Each query exercises a different plugin.

### NPI Registry — Provider Lookup

```
Look up NPI 1003000126
```
**Expected:** Provider name, specialty, address, license state, active status.

```
Search for cardiologists named Smith in Texas
```
**Expected:** List of matching providers with NPI, credential, specialty.

```
Verify that NPI 1003000126 is an active provider
```
**Expected:** Credential confirmation with NPPES active/inactive status.

---

### ICD-10 Codes — Code Search & Validation

```
Search ICD-10 codes for community-acquired pneumonia
```
**Expected:** List of codes including J18.9 (Pneumonia, unspecified organism).

```
Validate ICD-10 codes J18.9, E11.9, and Z87.891
```
**Expected:** Per-code validity, billability, and full description from ICD-10-CM 2025.

```
What ICD-10 chapter covers diseases of the respiratory system?
```
**Expected:** Chapter X (J00–J99) details and subcategory breakdown.

---

### CMS Coverage — Medicare Policy Search

```
What does Medicare cover for CT-guided lung biopsy?
```
**Expected:** Relevant LCD/NCD titles, policy IDs, medical necessity criteria.

```
Find Medicare coverage policies for continuous glucose monitoring
```
**Expected:** LCD for CGM devices, covered diagnoses, documentation requirements.

```
Show me recently updated CMS coverage determinations
```
**Expected:** List of NCDs/LCDs updated in the last 30 days.

---

## Use Case 1 — Differential Diagnosis from Symptoms

### Description
The chatbot uses ICD-10 code search to map symptoms to candidate diagnoses, then
cross-references CMS coverage policies to identify what documentation is needed
if the condition requires a procedure or device.

### Sample Queries

**Basic symptom mapping:**
```
A patient presents with productive cough, fever over 38.5°C, and right lower lobe
infiltrate on chest X-ray. What differential diagnoses should be considered and
what ICD-10 codes cover each?
```

**Multi-system presentation:**
```
Patient has fatigue, polyuria, polydipsia, and fasting glucose of 210 mg/dL.
Suggest differential diagnoses with ICD-10 codes and indicate which are most
likely given these lab values.
```

**Cardiology example:**
```
A 62-year-old male with exertional chest pain, diaphoresis, and ST-segment
elevation in leads II, III, aVF. List differential diagnoses ranked by likelihood,
ICD-10 codes for each, and what prior auth would be needed for urgent cath.
```

### Accuracy Verification
After the chatbot responds, ask it to cross-check the clinical logic:

```
For the diagnosis you ranked most likely, what does CMS Medicare policy say
about coverage criteria for the confirmatory workup?
```

```
Are all the ICD-10 codes you suggested billable in fiscal year 2025?
Validate them now.
```

---

## Use Case 2 — Drug Interaction Checks

### Description
The chatbot reasons about pharmacological interactions using clinical knowledge
and flags combinations known to carry serious risk. It can suggest ICD-10 codes
for related adverse events and identify whether prior auth is required for
alternative therapies.

> **Note:** The installed MCP servers cover NPI, ICD-10, and CMS coverage. Drug
> interaction checking uses Claude's clinical training. For production use, add a
> dedicated drug interaction MCP (e.g., DrugBank or OpenFDA connector).

### Sample Queries — Known Dangerous Combinations

**Warfarin + Aspirin (bleeding risk):**
```
A patient is on warfarin 5mg daily for atrial fibrillation and was just started
on aspirin 325mg for a recent NSTEMI. What interactions should I be aware of,
how serious is the risk, and what ICD-10 codes cover anticoagulant-related
adverse events?
```

**SSRIs + MAOIs (serotonin syndrome):**
```
Patient is on sertraline 100mg and their new psychiatrist wants to add phenelzine.
Flag any interactions, explain the mechanism, and provide ICD-10 codes for
serotonin syndrome. Does Medicare require prior auth for alternative SSRI
augmentation strategies?
```

**QT prolongation combination:**
```
Patient is on ciprofloxacin for a UTI and azithromycin for pneumonia overlap.
Both prolong the QT interval. What is the clinical risk, what monitoring is
needed, and what ICD-10 codes apply if an arrhythmia develops?
```

**ACE inhibitor + potassium-sparing diuretic:**
```
Patient on lisinopril 20mg and spironolactone 25mg. What is the hyperkalemia
risk, at what potassium level should we be concerned, and what ICD-10 code
covers drug-induced hyperkalemia?
```

### Verification Prompt
```
For each drug interaction you described, validate the ICD-10 adverse event codes
and confirm they are billable under ICD-10-CM 2025.
```

---

## Use Case 3 — Dosage Recommendations by Patient Profile

### Description
Tests the chatbot's ability to adjust dosing guidance based on patient-specific
factors and connects recommendations to ICD-10 codes and Medicare coverage where
applicable.

> **Note:** Dosing guidance uses Claude's clinical training. Always verify against
> current prescribing information before clinical use.

### Pediatric Patient

```
What is the appropriate amoxicillin dose for otitis media in a 4-year-old
weighing 18kg? Provide the ICD-10 code for acute otitis media and indicate
whether Medicare covers antibiotic therapy for this diagnosis.
```

```
A 7-year-old with asthma (weight 25kg) needs a short-course of prednisolone
for an acute exacerbation. What dose, frequency, and duration would you recommend?
Provide the ICD-10 codes for acute asthma exacerbation.
```

### Elderly Patient (≥ 65 years)

```
An 82-year-old with mild cognitive impairment is prescribed metformin for
newly diagnosed Type 2 diabetes. Are there Beers Criteria concerns? What dose
adjustments are recommended? Provide the relevant ICD-10 codes and check if
Medicare has a coverage policy for diabetes management programs.
```

```
A 75-year-old with a GFR of 48 mL/min is on apixaban for afib. Is the standard
dose of 5mg BID appropriate or should it be reduced? Show the ICD-10 codes for
atrial fibrillation and CKD stage 3.
```

### Renal Impairment

```
Patient has CKD Stage 4 (eGFR 22 mL/min) and requires vancomycin for MRSA
bacteremia. How should dosing and monitoring be adjusted? Provide ICD-10 codes
for CKD Stage 4, MRSA septicemia, and drug toxicity monitoring.
```

```
A patient with eGFR 30 mL/min needs gabapentin for diabetic neuropathy.
What maximum dose is safe, what are the signs of toxicity to watch for, and
what ICD-10 codes cover diabetic peripheral neuropathy?
```

### Cross-Profile Verification Prompt
```
For the renal impairment dosing you recommended, validate the ICD-10 codes
and check whether CMS Medicare has a coverage policy for the condition
being treated.
```

---

## Prior Authorization Walkthrough

### Full PA Scenario

```
Walk me through a prior authorization request for the following:
- Member: Jane Doe, ID M123456, DOB 05/14/1968, State: TX
- Procedure: CT-guided transbronchial lung biopsy, CPT 32408
- Diagnosis: R91.1 (solitary pulmonary nodule), suspected malignancy
- Ordering Provider NPI: 1003000126
- Clinical notes: 1.2cm right upper lobe nodule, non-calcified, growing on
  serial CT over 6 months. PET scan negative. Pulmonologist recommends tissue
  sampling prior to VATS resection.
```

This single query exercises all three MCP connectors:
1. **NPI MCP** — verifies the ordering provider
2. **ICD-10 MCP** — validates R91.1 and pulls coding details
3. **CMS Coverage MCP** — finds applicable LCD for lung biopsy coverage criteria

---

## Troubleshooting

| Issue | Resolution |
|-------|-----------|
| `Claude Code plugin registry not found` | Run `claude plugin install healthcare/fhir-developer` |
| `No MCP servers found` | Check `~/.claude/plugins/installed_plugins.json` exists |
| MCP server showing ❌ at startup | Verify plugin is installed; check network access to MCP endpoint |
| `ANTHROPIC_API_KEY not set` | Add key to `.env` in this directory |
| `mcp-client-2025-04-04 beta not supported` | Upgrade: `pip install anthropic --upgrade` |

---

## File Reference

| File | Purpose |
|------|---------|
| [pa_chatbot.py](pa_chatbot.py) | Main chatbot — plugin loader, MCP integration, chat loop |
| [CLAUDE.md](CLAUDE.md) | Project rules — MCP server URL policy |
| [requirements.txt](requirements.txt) | Python dependencies |
| [.env](`.env`) | API key config (not committed) |
