"""
CPG Sex & Gender Extraction Tool
Requirements: streamlit anthropic pymupdf pdfplumber pandas openpyxl python-dotenv requests
"""

import io
import json
import os
import time
from datetime import datetime

import anthropic
import fitz  # PyMuPDF
import pandas as pd
import pdfplumber
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="CPG Sex & Gender Extraction Tool",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  :root { --navy: #1a3c5e; --pale: #d0e4f5; }
  .tier-header {
    font-size: 1.05rem; font-weight: 700; color: #e8edf2;
    padding: 0.35rem 0; border-bottom: 2px solid #4a7fa8;
    margin: 1.4rem 0 0.8rem 0;
  }
  /* All custom boxes: explicit dark text for light + dark theme compatibility */
  .box-warn {
    background: #fff8e1; border-left: 4px solid #f59e0b;
    padding: .75rem 1rem; border-radius: 4px; margin: .5rem 0;
    color: #1a1a1a !important;
  }
  .box-info {
    background: #eff6ff; border-left: 4px solid #3b82f6;
    padding: .75rem 1rem; border-radius: 4px; margin: .5rem 0;
    color: #1a1a1a !important;
  }
  .box-ok {
    background: #f0fdf4; border-left: 4px solid #22c55e;
    padding: .75rem 1rem; border-radius: 4px; margin: .5rem 0;
    color: #1a1a1a !important;
  }
  .box-warn *, .box-info *, .box-ok * { color: #1a1a1a !important; }
  /* Evidence block for Tier 2 AI evidence display */
  .evidence-block {
    background: #f3f4f6; border-left: 3px solid #9ca3af;
    padding: 0.45rem 0.75rem; border-radius: 0 4px 4px 0;
    font-size: 0.83rem; color: #374151 !important;
    margin: 0.15rem 0 0.75rem 0; line-height: 1.4;
  }
  .evidence-block * { color: #374151 !important; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PROMPTS
# ══════════════════════════════════════════════════════════════════════════════

# Fix 2 + 5: Tier 2 evidence fields added; Fix 5 boundary condition added
SYSTEM_PROMPT = """\
You are a systematic review data extractor with expertise in sex and gender health research. \
Extract structured data from clinical practice guidelines (CPGs) according to the schema below.

Return ONLY a single valid JSON object. No preamble, no explanation, no markdown fences.

═══════════════════════════════════════════════════════
OUTPUT SCHEMA
═══════════════════════════════════════════════════════
{
  "tier1": {
    "guideline_title":           "<full title>",
    "publication_year":          "<year>",
    "update_year":               "<year or 'Not reported'>",
    "country_of_origin":         "<country or 'International'>",
    "organisation_publisher":    "<publisher>",
    "authors":                   "<named individual authors if listed; if none, the authoring group or committee name as it appears on the document (e.g. 'NICE Guideline Committee'); 'Not reported' only if no authoring information of any kind is present>",
    "guideline_type":            "<CPG | Clinical care standard | Guide>",
    "musculoskeletal_condition": "<MSK condition addressed>"
  },
  "tier2": {
    "sg_total_mentions":                    <integer — total count of sex/gender term occurrences>,
    "sg_example_context":                   "<brief description of main contexts, or 'NA'>",
    "mention_of_sex_or_gender":             "<Sex only | Gender only | Both | Neither>",
    "mention_of_sex_or_gender_evidence":    "<direct quote supporting the rating, or fallback — see evidence rules>",
    "definitions_provided":                 "<Yes | No>",
    "definitions_provided_evidence":        "<direct quote of definition if Yes; fallback if No>",
    "definitions_text":                     "<quoted text if Yes, else 'Not applicable'>",
    "correct_usage_overall":                "<Correct | Unclear | Incorrect>",
    "correct_usage_overall_evidence":       "<direct quote illustrating correct, unclear, or incorrect usage>",
    "nonbinary_use":                        "<Nonbinary | Binary | Unclear>",
    "nonbinary_use_evidence":               "<direct quote supporting the rating>",
    "appropriate_categories":               "<Appropriate | Inappropriate | Unclear>",
    "appropriate_categories_evidence":      "<direct quote supporting the rating>",
    "non_interchangeability":               "<Noninterchangeable | Interchangeable | Unclear>",
    "non_interchangeability_evidence":      "<direct quote showing interchangeable or distinct usage>"
  },
  "tier3": {
    "pathophysiology":           {"rating": <1|2|3>, "evidence": "<direct quote or fallback>"},
    "epidemiology":              {"rating": <1|2|3>, "evidence": "<direct quote or fallback>"},
    "clinical_manifestation":    {"rating": <1|2|3>, "evidence": "<direct quote or fallback>"},
    "diagnosis":                 {"rating": <1|2|3>, "evidence": "<direct quote or fallback>"},
    "prognosis":                 {"rating": <1|2|3>, "evidence": "<direct quote or fallback>"},
    "risk_factors":              {"rating": <1|2|3>, "evidence": "<direct quote or fallback>"},
    "treatment_and_management":  {"rating": <1|2|3>, "evidence": "<direct quote or fallback>"},
    "rehabilitation":            {"rating": <1|2|3>, "evidence": "<direct quote or fallback>"},
    "preventive_strategies":     {"rating": <1|2|3>, "evidence": "<direct quote or fallback>"},
    "cumulative_domain_score":   <integer, sum of all nine ratings>
  },
  "tier3b": {
    "chair_members":                "<'Not reported' or list of name strings>",
    "clinicians_and_commissioners": "<'Not reported' or list of name strings>",
    "lay_members":                  "<'Not reported' or list of name strings>"
  },
  "overall_rating": {
    "category":  <integer 1-5>,
    "rationale": "<brief synthesis rationale>"
  }
}

═══════════════════════════════════════════════════════
TIER 2 — SEX/GENDER TERM COUNTING (sg_total_mentions)
═══════════════════════════════════════════════════════
Count total occurrences of ONLY these terms: sex, gender, male, female, intersex, man, men, woman, women, trans, non-binary, nonbinary, genderfluid, genderdiverse, agender, pregnan*, fertil*, menopaus* and their inflected forms (males, females, transgender, etc.).
STRICT EXCLUSION — do NOT count and do NOT include in sg_total_mentions: he, she, his, her, him, himself, herself, "he or she", "his or her", "his/her", "he/she". These are grammatical pronouns, not sex or gender terms. If the only sex/gender-related content is pronoun usage of this kind, set sg_total_mentions = 0 and mention_of_sex_or_gender = "Neither".
sg_example_context: 1–3 sentences on main contexts terms appear; "NA" if none found.

TIER 2 EVIDENCE RULES (applies to all six *_evidence fields):
• Provide a verbatim quote from the guideline that directly supports the rating decision.
• If sex and gender terms are entirely absent from the guideline, return:
  "No sex or gender related terms identified in this guideline."
• If terms are present but usage is ambiguous, return a direct quote that shows the ambiguous usage.
• Never return an empty string or null for any evidence field.

═══════════════════════════════════════════════════════
TIER 3 RATING SCALE
═══════════════════════════════════════════════════════
1 = No mention of sex or gender in relation to this domain
2 = Superficial mention — states a difference exists but no clinical implications or actionable guidance
3 = Substantial mention — specific recommendations, data, or management differences by sex or gender

For each domain, evidence must be a direct verbatim quote from the guideline.
  • If no relevant content: evidence = "No relevant content identified", rating = 1
  • If domain is structurally absent from guideline: evidence = "Domain not covered in guideline", rating = 1
cumulative_domain_score = arithmetic sum of the nine domain ratings (range 9–27).

═══════════════════════════════════════════════════════
OVERALL CATEGORY DEFINITIONS
═══════════════════════════════════════════════════════
1 — Evidence-informed recommendations supporting different or singular approaches for men and women
2 — Sex-specific reference values for laboratory or clinical data
3 — Sex/gender differences in epidemiologic features or risk factors, without clinical management suggestions
4 — Superficial mention of sex or gender only
5 — No mention of sex or gender

The overall category must be derived as a logical synthesis of Tier 2 and Tier 3 findings.

═══════════════════════════════════════════════════════
MANDATORY BOUNDARY CONDITIONS
═══════════════════════════════════════════════════════
1. INTERCHANGEABLE TERMINOLOGY
   If the guideline uses sex and gender interchangeably — e.g. "gender" to mean biological attributes,
   or "male/female" to mean social roles — set non_interchangeability = "Interchangeable" and reflect
   this in correct_usage_overall.

2. TANGENTIAL DOMAIN CONTENT
   Content tangentially related to a domain but not substantively addressing sex/gender differences
   (e.g. noting higher female prevalence without discussing clinical implications) must be rated 2, not 3.

3. PREGNANCY OR FERTILITY ONLY
   If the only sex- or gender-related content concerns pregnancy, fertility, or menopause without
   broader clinical application, set overall category = 4, not 1–3.

4. MISSING COMMITTEE LIST
   If no committee membership list is present, return "Not reported" for all three tier3b fields.

5. PARSING FAILURES
   If any field cannot be reliably extracted, return "Section not clearly parsed". Never return null.

6. DOCUMENT ISOLATION
   Each document is processed in complete isolation.

7. TIER 2 EVIDENCE FOR ABSENT OR AMBIGUOUS TERMS
   For any Tier 2 field where sex and gender terms are entirely absent from the guideline, return the
   evidence field as "No sex or gender related terms identified in this guideline."
   For any field where terms are present but usage is ambiguous, return a direct quote showing the
   ambiguous usage rather than a paraphrase.

8. FUTURE RESEARCH SUGGESTIONS
   Sentences or passages that recommend further study, call for additional research, or note that sex
   or gender subgroups should be investigated in future do not constitute sex- or gender-specific
   clinical content. They must not elevate a domain rating above 1. Only current, actionable clinical
   content counts toward domain ratings.\
"""

# AGREE II system prompt — full per-item criteria, 1-7 scale
AGREE_II_SYSTEM_PROMPT = """\
You are assessing this clinical practice guideline using the AGREE II instrument.
For each of the 23 items, assess every individual criterion using the five-point
continuum below. Do NOT assign a numeric score — Python calculates scores from
your criterion labels. Your only job is accurate criterion-level assessment.

Return ONLY a single valid JSON object. No preamble, no explanation, no markdown fences.

════════════════════════════════════════════════════
MANDATORY ASSESSMENT RULES
════════════════════════════════════════════════════

RULE A — APPENDIX RULE:
If the main document explicitly states that information exists and directs the
reader to a named appendix, supplementary file, or eAppendix, treat that
criterion as FULLY MET. Do NOT mark a criterion unmet because detail is in an
appendix rather than the main text. Only treat a criterion as unmet if the main
document makes no reference to that information being available anywhere.

RULE B — SCOPE-APPROPRIATE APPRAISAL:
Apply each criterion in the context of what is relevant to this guideline's scope.
Do not penalise a guideline for omitting details genuinely not applicable to it.
A guideline covering all adults with a named condition satisfies age and population
criteria without requiring sex/gender specification if that is not the scope.

RULE C — CRITERION LABELS:
For each criterion, assign exactly one of these five labels:
  "Fully met"     — criterion completely and clearly satisfied
  "Mostly met"    — criterion substantially satisfied with only a minor gap
  "Partially met" — criterion approximately half satisfied
  "Minimally met" — criterion barely touched; only a small element present
  "Not met"       — criterion entirely absent

SEQUENCING for every item:
  1. Apply Rule A — appendix references count as fully met
  2. Apply Rule B — exclude criteria genuinely not applicable to this guideline
  3. Assess each remaining criterion individually using the five labels above
  4. Write a rationale paragraph explicitly naming each criterion and its label
     e.g. "Criterion 1 (databases) fully met: ... Criterion 2 (time periods) fully met: ..."

════════════════════════════════════════════════════
DOMAIN 1 — SCOPE AND PURPOSE
════════════════════════════════════════════════════

Item 1 (D1_Objectives_Described) — The overall objective(s) of the guideline is (are) specifically described.
Criteria: (1) health intent described (prevention/screening/diagnosis/treatment); (2) expected benefit or outcome specified — any statement of intended improvement satisfies this; quantification is NOT required; (3) target population or society identified.
Where to look: introduction, scope, purpose, rationale, background, objectives.
NOTE: Objectives stated across introduction and rationale sections satisfy this item; a dedicated objectives section is NOT required.

Item 2 (D1_HealthQuestions_Described) — The health question(s) covered by the guideline is (are) specifically described.
Criteria: (1) target population specified; (2) interventions or exposures described; (3) comparisons stated if appropriate — PICO questions referenced in a named appendix = fully met; comparisons implied within recommendation topics also satisfy this; (4) outcomes described — outcomes mentioned within recommendations satisfy this; a separate a priori list is NOT required; (5) health care setting or context described — a statement that the guideline applies across "many different settings" or to multiple provider types satisfies this; naming specific settings is NOT required.
Where to look: introduction, scope, purpose, rationale, background, questions.

Item 3 (D1_Population_Described) — The population to whom the guideline is meant to apply is specifically described.
Criteria: (1) target population and age range — stating "adults" satisfies the age criterion; sex/gender only required if the guideline has a sex/gender-specific scope restriction; (2) clinical condition described if relevant; (3) severity or stage described if relevant — description within recommendations satisfies this; (4) comorbidities described if relevant — discussed as prognostic factors within recommendations satisfies this; (5) excluded populations — stating one exclusion (e.g., paediatric patients) is fully met if no other exclusions exist.
Where to look: introduction, scope, patient population sections, individual recommendations.

════════════════════════════════════════════════════
DOMAIN 2 — STAKEHOLDER INVOLVEMENT
════════════════════════════════════════════════════

Item 4 (D2_RelevantProfessionals_Included) — The guideline development group includes individuals from all relevant professional groups.
Criteria: (1) name provided for each member; (2) discipline or content expertise provided; (3) institution — professional society affiliation (e.g., AAOS, APTA) FULLY satisfies this; employing hospital is NOT additionally required; (4) geographical location — must be explicitly provided per individual member or per their employing institution; the headquarters location of the professional society they represent does NOT satisfy this criterion; implicit geographic inference does NOT satisfy this; NOT MET if individual or institutional locations are not stated; (5) role in development — chair, co-chair, or voting/non-voting designations satisfy this; per-member task descriptions are NOT required. Additional: methodology expert present (statistician, librarian, or systematic review expert).
Where to look: introduction, acknowledgements, methods, panel member list.

Item 5 (D2_TargetPopViews_Sought) — The views and preferences of the target population have been sought.
Criteria: (1) strategy for capturing patient/public views stated; (2) methods by which views were sought described; (3) outcomes or information gathered from patient/public described; (4) how information was used to inform guideline development described.
NOTE: Professional body commentary does NOT constitute patient or public involvement.
Where to look: scope, methods, external review, target population perspectives sections.

Item 6 (D2_TargetUsers_Defined) — The target users of the guideline are clearly defined.
Criteria: (1) clear description of intended audience; (2) description of how the guideline may be used — a general statement of intended use satisfies this; per-user-group differentiation is NOT required.
Where to look: introduction, target user, intended user sections.

════════════════════════════════════════════════════
DOMAIN 3 — RIGOUR OF DEVELOPMENT
════════════════════════════════════════════════════

Item 7 (D3_SystematicSearch_Used) — Systematic methods were used to search for evidence.
Criteria: (1) named electronic database(s) or evidence source(s); (2) time periods searched; (3) search terms used — FULLY MET if referenced to a named appendix; (4) full search strategy included — FULLY MET if referenced to a named appendix.
Where to look: methods, literature search strategy, appendices.

Item 8 (D3_SelectionCriteria_Described) — The criteria for selecting the evidence are clearly described.
Criteria: (1) inclusion criteria — FULLY MET if "a priori inclusion criteria" referenced to a named appendix, or if a high-level description of the inclusion approach appears in the main text; (2) exclusion criteria — FULLY MET if excluded articles referenced to a named appendix or if exclusion reasons appear anywhere in the main text or attrition flowchart.
Where to look: methods, literature search, inclusion/exclusion criteria, attrition flowchart, appendices.

Item 9 (D3_EvidenceStrengthsLimits_Described) — The strengths and limitations of the body of evidence are clearly described.
Criteria: (1) evidence evaluated for bias — a structured quality rating system (High/Moderate/Low applied consistently) satisfies this; naming the specific tool is NOT required; (2) how evidence was interpreted — rationale sections within recommendations satisfy this; (3) aspects addressed: study design, consistency, direction, magnitude, applicability — coverage distributed across recommendation rationale sections satisfies this.
Where to look: methods, results, discussion, evidence tables, individual recommendation rationale sections.

Item 10 (D3_FormulationMethods_Described) — The methods for formulating the recommendations are clearly described.
Criteria: (1) description of the recommendation development process — meetings, literature review, evidence synthesis, voting satisfies this; (2) outcomes of the process — resulting recommendations and strength ratings satisfy this; (3) how the process influenced recommendations — explicit mapping between evidence quality and recommendation strength satisfies this; a named framework is NOT required; noting when recommendations were downgraded satisfies this.
Where to look: methods, guideline development process sections.

Item 11 (D3_BenefitsRisks_Considered) — The health benefits, side effects, and risks have been considered in formulating the recommendations.
Criteria: (1) supporting data and report of benefits; (2) supporting data and report of harms — FULLY MET if a dedicated harms subsection is structurally present for each recommendation; brief or null entries do NOT make this unmet if the section exists throughout; (3) balance between benefits and harms reported — met if discussed for recommendations where clinically relevant; not every recommendation requires explicit tradeoff discussion; (4) recommendations reflect considerations of both — met if the majority reference both benefit and harm evidence.
Where to look: methods, interpretation, discussion, recommendations, risks and harms subsections.

Item 12 (D3_Link_EvidenceToRecs) — There is an explicit link between the recommendations and the supporting evidence.
Criteria: (1) guideline describes how development group linked evidence to recommendations; (2) each recommendation linked to evidence — named study citations within rationale sections satisfy this; (3) recommendations linked to evidence summaries or tables — FULLY MET if narrative summaries present in rationale sections OR evidence tables referenced in a named appendix.
Where to look: recommendations, key evidence sections, appendices.

Item 13 (D3_ExternalReview_Conducted) — The guideline has been externally reviewed by experts prior to its publication.
Criteria: (1) purpose and intent of external review described — any statement of the reason for review satisfies this; (2) methods used described — description of review period and comment format satisfies this, even if brief; (3) description of external reviewers — PARTIALLY MET if the professional bodies or committees from which reviewers are drawn are named (e.g., Board of Directors, specialty societies) but individual names, professions, or credentials are not provided; NOT MET only if no information whatsoever is given about who the reviewers are; FULLY MET only if individual reviewer names or professional credentials are provided; (4) outcomes gathered — FULLY MET if outcomes referenced in a named document even if not reproduced; apply Rule A; (5) how information was used — a statement that the draft was modified in response to review partially satisfies this.
Where to look: methods, results, acknowledgements, peer review sections.

Item 14 (D3_UpdateProcedure_Provided) — A procedure for updating the guideline is provided.
Criteria: (1) statement that guideline will be updated; (2) explicit time interval or triggering criteria — a stated time interval (e.g., five years) satisfies this; named triggers also satisfy this; (3) methodology for updating — stating triggers and/or time interval IS the methodology; detailed procedural description is NOT required.
Where to look: introduction, methods, guideline update, closing sections.

════════════════════════════════════════════════════
DOMAIN 4 — CLARITY OF PRESENTATION
════════════════════════════════════════════════════

Item 15 (D4_Recs_Specific_Unambiguous) — The recommendations are specific and unambiguous.
Criteria: (1) statement of the recommended action — evidence summary framing is acceptable if the clinical implication is clear; (2) identification of intent or purpose; (3) identification of the relevant population — met if specified in the majority of recommendations; (4) caveats or qualifying statements if relevant — met if present where clinically warranted. Consensus statements acknowledging insufficient evidence are NOT a failure of this item.
Where to look: recommendations, executive summary sections.

Item 16 (D4_ManagementOptions_Presented) — The different options for management of the condition or health issue are clearly presented.
Criteria: (1) description of options; (2) description of population or clinical situation most appropriate to each option.
NOTE: Absence of a flowchart does NOT reduce the score where both criteria are substantively met.
Where to look: executive summary, recommendations, discussion, treatment options sections.

Item 17 (D4_KeyRecs_Identifiable) — Key recommendations are easily identifiable.
Criteria: (1) key recommendations presented in summarised box, bold, underlined, or as flow charts/algorithms — bold text in a dedicated summary section satisfies this; a flowchart is one option among several, NOT a requirement; (2) specific recommendations grouped together in one section.
Where to look: executive summary, conclusions, recommendations sections.

════════════════════════════════════════════════════
DOMAIN 5 — APPLICABILITY
════════════════════════════════════════════════════

Item 18 (D5_BarriersFacilitators_Described) — The guideline describes facilitators and barriers to its application.
Criteria: (1) identification of types of facilitators and barriers considered; (2) methods by which information on facilitators/barriers was sought; (3) information or description of facilitators/barriers that emerged; (4) how this influenced guideline development or recommendations.
NOTE: Dissemination plans (webinars, CME channels) describe distribution, NOT implementation barriers — they do NOT satisfy these criteria.
Where to look: dissemination/implementation, quality indicators, barriers sections.

Item 19 (D5_ApplicationTools_Provided) — The guideline provides advice and/or tools on how the recommendations can be put into practice.
Criteria: (1) implementation section present — a dissemination plans section is partially met at most; fully met requires guidance on how to implement recommendations, not just distribute them; (2) tools and resources present — a website URL or app reference alone is NOT MET for this criterion; actual clinical tools (checklists, algorithms, decision aids, how-to manuals) must be present in the document or a referenced appendix for this criterion to reach minimally met or above; (3) directions on how to access tools — a bare website URL or app store reference without contextual guidance on what the tool contains or how to use it for this specific guideline is PARTIALLY MET; fully or mostly met requires more substantive directions or a description of tool content.
Where to look: implementation, tools, resources, appendices sections.

Item 20 (D5_ResourceImplications_Considered) — The potential resource implications of applying the recommendations have been considered.
Criteria: (1) types of cost information considered identified; (2) methods by which cost information was sought described; (3) cost findings described; (4) how cost information was used to inform guideline development.
Where to look: methods, cost utility, cost effectiveness, budget implications sections.

Item 21 (D5_MonitoringCriteria_Presented) — The guideline presents monitoring and/or auditing criteria.
Criteria: (1) monitoring or auditing criteria provided; (2) criteria clearly derived from key recommendations; (3) type of measure specified (process, behavioural, clinical, or outcome).
NOTE: Future research suggestions are NOT equivalent to monitoring criteria.
Where to look: recommendations, quality indicators, monitoring, audit sections.

════════════════════════════════════════════════════
DOMAIN 6 — EDITORIAL INDEPENDENCE
════════════════════════════════════════════════════

Item 22 (D6_FundingBody_NoInfluence) — The views of the funding body have not influenced the content of the guideline.
Criteria: (1) name of funding body provided; (2) explicit statement that views or interests of the funding body have not influenced the final recommendations — FULLY MET only if there is an explicit statement that the funding body did not influence the recommendations; MOSTLY MET if the statement only excludes external commercial funding but the developing organisation is also the funder (i.e., the statement addresses commercial influence but does not explicitly address the developing organisation's own potential influence); structural independence (e.g., independent physician volunteer panel, multi-committee approval) contributes to this criterion but does not alone satisfy it.
Where to look: preface, methods, acknowledgements, funding sections.

Item 23 (D6_CompetingInterests_Recorded) — Competing interests of members of the guideline development group have been recorded and addressed.
Criteria: (1) statement that interests were sought; (2) types of interests sought described; (3) methods by which interests were sought and recorded described; (4) how interests identified were addressed — disclosure and reporting of individual conflicts satisfies this; explicit recusal procedures are NOT required for this criterion to be met or mostly met.
Where to look: preface, methods, acknowledgements, appendices, conflict of interest sections.

════════════════════════════════════════════════════
OUTPUT SCHEMA — criterion labels only, NO numeric scores:
════════════════════════════════════════════════════
{
  "D1_Objectives_Described":               {"c1": "<label>", "c2": "<label>", "c3": "<label>", "rationale": "<paragraph naming each criterion and its label>"},
  "D1_HealthQuestions_Described":          {"c1": "<label>", "c2": "<label>", "c3": "<label>", "c4": "<label>", "c5": "<label>", "rationale": "<paragraph>"},
  "D1_Population_Described":               {"c1": "<label>", "c2": "<label>", "c3": "<label>", "c4": "<label>", "c5": "<label>", "rationale": "<paragraph>"},
  "D2_RelevantProfessionals_Included":     {"c1": "<label>", "c2": "<label>", "c3": "<label>", "c4": "<label>", "c5": "<label>", "rationale": "<paragraph>"},
  "D2_TargetPopViews_Sought":              {"c1": "<label>", "c2": "<label>", "c3": "<label>", "c4": "<label>", "rationale": "<paragraph>"},
  "D2_TargetUsers_Defined":                {"c1": "<label>", "c2": "<label>", "rationale": "<paragraph>"},
  "D3_SystematicSearch_Used":              {"c1": "<label>", "c2": "<label>", "c3": "<label>", "c4": "<label>", "rationale": "<paragraph>"},
  "D3_SelectionCriteria_Described":        {"c1": "<label>", "c2": "<label>", "rationale": "<paragraph>"},
  "D3_EvidenceStrengthsLimits_Described":  {"c1": "<label>", "c2": "<label>", "c3": "<label>", "rationale": "<paragraph>"},
  "D3_FormulationMethods_Described":       {"c1": "<label>", "c2": "<label>", "c3": "<label>", "rationale": "<paragraph>"},
  "D3_BenefitsRisks_Considered":           {"c1": "<label>", "c2": "<label>", "c3": "<label>", "c4": "<label>", "rationale": "<paragraph>"},
  "D3_Link_EvidenceToRecs":                {"c1": "<label>", "c2": "<label>", "c3": "<label>", "rationale": "<paragraph>"},
  "D3_ExternalReview_Conducted":           {"c1": "<label>", "c2": "<label>", "c3": "<label>", "c4": "<label>", "c5": "<label>", "rationale": "<paragraph>"},
  "D3_UpdateProcedure_Provided":           {"c1": "<label>", "c2": "<label>", "c3": "<label>", "rationale": "<paragraph>"},
  "D4_Recs_Specific_Unambiguous":          {"c1": "<label>", "c2": "<label>", "c3": "<label>", "c4": "<label>", "rationale": "<paragraph>"},
  "D4_ManagementOptions_Presented":        {"c1": "<label>", "c2": "<label>", "rationale": "<paragraph>"},
  "D4_KeyRecs_Identifiable":               {"c1": "<label>", "c2": "<label>", "rationale": "<paragraph>"},
  "D5_BarriersFacilitators_Described":     {"c1": "<label>", "c2": "<label>", "c3": "<label>", "c4": "<label>", "rationale": "<paragraph>"},
  "D5_ApplicationTools_Provided":          {"c1": "<label>", "c2": "<label>", "c3": "<label>", "rationale": "<paragraph>"},
  "D5_ResourceImplications_Considered":    {"c1": "<label>", "c2": "<label>", "c3": "<label>", "c4": "<label>", "rationale": "<paragraph>"},
  "D5_MonitoringCriteria_Presented":       {"c1": "<label>", "c2": "<label>", "c3": "<label>", "rationale": "<paragraph>"},
  "D6_FundingBody_NoInfluence":            {"c1": "<label>", "c2": "<label>", "rationale": "<paragraph>"},
  "D6_CompetingInterests_Recorded":        {"c1": "<label>", "c2": "<label>", "c3": "<label>", "c4": "<label>", "rationale": "<paragraph>"},
  "AGREEII_Recommendation":               "<2-4 sentence narrative summary>"
}\
"""


USER_PROMPT_TEMPLATE = (
    "Extract structured data from the following clinical practice guideline.\n\n"
    "GUIDELINE TEXT:\n{text}"
)

AGREE_II_USER_PROMPT = (
    "Assess the following clinical practice guideline using the AGREE II framework.\n\n"
    "GUIDELINE TEXT:\n{text}"
)

# ══════════════════════════════════════════════════════════════════════════════
# AGREE II DOMAIN STRUCTURE
# ══════════════════════════════════════════════════════════════════════════════

AGREE_II_DOMAINS = [
    {
        "key": "D1", "name": "Domain 1 — Scope and Purpose",
        "score_col": "D1_Score_Scope and Purpose_%",
        "items": [
            ("D1_Objectives_Described",
             "Item 1: The overall objective(s) of the guideline is (are) specifically described",
             "D1_Objectives_Rationale"),
            ("D1_HealthQuestions_Described",
             "Item 2: The health question(s) covered by the guideline is (are) specifically described",
             "D1_HealthQuestions_Rationale"),
            ("D1_Population_Described",
             "Item 3: The population to whom the guideline is meant to apply is specifically described",
             "D1_Population_Rationale"),
        ],
    },
    {
        "key": "D2", "name": "Domain 2 — Stakeholder Involvement",
        "score_col": "D2_Score_Stakeholder Involvement_%",
        "items": [
            ("D2_RelevantProfessionals_Included",
             "Item 4: The guideline development group includes individuals from all relevant professional groups",
             "D2_RelevantProfessionals_Rationale"),
            ("D2_TargetPopViews_Sought",
             "Item 5: The views and preferences of the target population have been sought",
             "D2_TargetPopViews_Rationale"),
            ("D2_TargetUsers_Defined",
             "Item 6: The target users of the guideline are clearly defined",
             "D2_TargetUsers_Rationale"),
        ],
    },
    {
        "key": "D3", "name": "Domain 3 — Rigour of Development",
        "score_col": "D3_Score_Rigour of Development_%",
        "items": [
            ("D3_SystematicSearch_Used",
             "Item 7: Systematic methods were used to search for evidence",
             "D3_SystematicSearch_Rationale"),
            ("D3_SelectionCriteria_Described",
             "Item 8: The criteria for selecting the evidence are clearly described",
             "D3_SelectionCriteria_Rationale"),
            ("D3_EvidenceStrengthsLimits_Described",
             "Item 9: The strengths and limitations of the body of evidence are clearly described",
             "D3_EvidenceStrengthsLimits_Rationale"),
            ("D3_FormulationMethods_Described",
             "Item 10: The methods for formulating the recommendations are clearly described",
             "D3_FormulationMethods_Rationale"),
            ("D3_BenefitsRisks_Considered",
             "Item 11: The health benefits, side effects and risks have been considered in formulating the recommendations",
             "D3_BenefitsRisks_Rationale"),
            ("D3_Link_EvidenceToRecs",
             "Item 12: There is an explicit link between the recommendations and the supporting evidence",
             "D3_Link_Rationale"),
            ("D3_ExternalReview_Conducted",
             "Item 13: The guideline has been externally reviewed by experts prior to publication",
             "D3_ExternalReview_Rationale"),
            ("D3_UpdateProcedure_Provided",
             "Item 14: A procedure for updating the guideline is provided",
             "D3_UpdateProcedure_Rationale"),
        ],
    },
    {
        "key": "D4", "name": "Domain 4 — Clarity of Presentation",
        "score_col": "D4_Score_Clarity of Presentation_%",
        "items": [
            ("D4_Recs_Specific_Unambiguous",
             "Item 15: The recommendations are specific and unambiguous",
             "D4_Recs_Specific_Rationale"),
            ("D4_ManagementOptions_Presented",
             "Item 16: The different options for management of the condition are clearly presented",
             "D4_ManagementOptions_Rationale"),
            ("D4_KeyRecs_Identifiable",
             "Item 17: Key recommendations are easily identifiable",
             "D4_KeyRecs_Rationale"),
        ],
    },
    {
        "key": "D5", "name": "Domain 5 — Applicability",
        "score_col": "D5_Score_Applicability_%",
        "items": [
            ("D5_BarriersFacilitators_Described",
             "Item 18: The guideline describes facilitators of and barriers to its application",
             "D5_BarriersFacilitators_Rationale"),
            ("D5_ApplicationTools_Provided",
             "Item 19: The guideline provides advice or tools on how recommendations can be put into practice",
             "D5_ApplicationTools_Rationale"),
            ("D5_ResourceImplications_Considered",
             "Item 20: The potential resource implications of applying the recommendations have been considered",
             "D5_ResourceImplications_Rationale"),
            ("D5_MonitoringCriteria_Presented",
             "Item 21: The guideline presents monitoring or auditing criteria",
             "D5_MonitoringCriteria_Rationale"),
        ],
    },
    {
        "key": "D6", "name": "Domain 6 — Editorial Independence",
        "score_col": "D6_Score_Editorial Independence_%",
        "items": [
            ("D6_FundingBody_NoInfluence",
             "Item 22: The views of the funding body have not influenced the content of the guideline",
             "D6_FundingBody_Rationale"),
            ("D6_CompetingInterests_Recorded",
             "Item 23: Competing interests of members of the guideline development group have been recorded and addressed",
             "D6_CompetingInterests_Rationale"),
        ],
    },
]

AGREE_RATING_OPTIONS = [
    "1 - Strongly Disagree",
    "2 - Disagree",
    "3 - Somewhat Disagree",
    "4 - Neither Agree nor Disagree",
    "5 - Somewhat Agree",
    "6 - Agree",
    "7 - Strongly Agree",
]
AGREE_DEFAULT = "4 - Neither Agree nor Disagree"


def agree_rating_to_option(val) -> str:
    """Map API integer (1–7) or existing option string to the matching AGREE_RATING_OPTIONS entry."""
    try:
        n = int(str(val)[0])
        if 1 <= n <= 7:
            return AGREE_RATING_OPTIONS[n - 1]
    except (ValueError, IndexError):
        pass
    return AGREE_DEFAULT


def agree_item_score(rating: str) -> int:
    """Extract integer score (1–7) from a rating string like '7 - Strongly Agree'."""
    try:
        n = int(str(rating)[0])
        if 1 <= n <= 7:
            return n
    except (ValueError, IndexError):
        pass
    return 4


def calc_domain_score(ratings: list[str]) -> float:
    """AGREE II domain score using the standard per-domain formula.
    For a single appraiser on a 1–7 scale: min = n, max = 7n.
    Score = (obtained − n) / (6n) × 100."""
    n = len(ratings)
    obtained = sum(agree_item_score(r) for r in ratings)
    return round((obtained - n) / (n * 6) * 100, 1)


def overall_quality_label(domain_scores: list[float]) -> str:
    above_60 = sum(1 for s in domain_scores if s > 60)
    if above_60 >= 5:
        return "High quality"
    if above_60 >= 3:
        return "Average quality"
    return "Low quality"


TIER3_DOMAINS: list[tuple[str, str]] = [
    ("pathophysiology",          "Pathophysiology"),
    ("epidemiology",             "Epidemiology"),
    ("clinical_manifestation",   "Clinical manifestation"),
    ("diagnosis",                "Diagnosis"),
    ("prognosis",                "Prognosis"),
    ("risk_factors",             "Risk factors"),
    ("treatment_and_management", "Treatment and management"),
    ("rehabilitation",           "Rehabilitation"),
    ("preventive_strategies",    "Preventive strategies"),
]

RATING_OPTIONS = [
    "1 — No mention",
    "2 — Superficial mention",
    "3 — Substantial mention",
]

# Sign-off checkbox keys (Fix 4)
SIGNOFF_KEYS = [
    "signoff_tier1", "signoff_tier2", "signoff_tier3",
    "signoff_tier3b", "signoff_overall", "signoff_agreeii",
]
SIGNOFF_TEXT = (
    "I have reviewed all fields in this section and confirm the "
    "AI-generated outputs are accurate or have been corrected."
)

# ══════════════════════════════════════════════════════════════════════════════
# PDF HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def extract_text_pymupdf(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)


def extract_text_pdfplumber(pdf_bytes: bytes) -> str:
    chunks: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                t = page.extract_text()
                if t:
                    chunks.append(t)
            except Exception as e:
                chunks.append(f"[Page {i+1}: extraction failed — {e}]")
    return "\n".join(chunks)


def character_yield(text: str, file_bytes: int) -> float:
    return len(text) / file_bytes if file_bytes else 0.0


# ══════════════════════════════════════════════════════════════════════════════
# DETERMINISTIC S/G TERM COUNTER
# Counts occurrences of permitted sex/gender terms only.
# Gendered pronouns (he, she, his, her, him, himself, herself) and pronoun
# phrases (he or she, his/her, etc.) are explicitly excluded regardless of
# what the LLM returns. This function overrides the LLM's sg_total_mentions.
# ══════════════════════════════════════════════════════════════════════════════

import re as _re

# Permitted terms per the parent review protocol search strategy
_SG_PATTERNS = [
    r'\bsex\b', r'\bgender\b',
    r'\bmale[s]?\b', r'\bfemale[s]?\b', r'\bintersex\b',
    r'\bman\b', r'\bmen\b', r'\bwoman\b', r'\bwomen\b',
    r'\btrans\b', r'\btransgender\b', r'\btranssexual\b',
    r'\bnon-binary\b', r'\bnonbinary\b',
    r'\bgenderfluid\b', r'\bgender-fluid\b',
    r'\bgenderdiverse\b', r'\bgender-diverse\b',
    r'\bagender\b',
    r'\bpregnan\w*\b', r'\bfertil\w*\b', r'\bmenopaus\w*\b',
]

# Pronoun phrases to strip BEFORE counting so they cannot match permitted terms
# (e.g. "he or she" contains no permitted terms but "she" alone would match
#  if we searched naively — we strip the phrase first)
_PRONOUN_STRIP = _re.compile(
    r'\b(he\s+or\s+she|she\s+or\s+he|his\s+or\s+her|her\s+or\s+his'
    r'|his/her|her/his|he/she|she/he'
    r'|himself|herself|him|his|her|she|he)\b',
    _re.IGNORECASE
)

_SG_COMPILED = [_re.compile(p, _re.IGNORECASE) for p in _SG_PATTERNS]


def count_sg_terms(text: str) -> int:
    """Return deterministic count of permitted S/G terms, excluding pronouns."""
    # Remove pronoun phrases first so they cannot contribute to the count
    scrubbed = _PRONOUN_STRIP.sub(" ", text)
    return sum(len(p.findall(scrubbed)) for p in _SG_COMPILED)

def call_claude(api_key: str, system: str, user_text: str, max_tokens: int = 8192) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_text}],
    )
    return response.content[0].text


def parse_json_response(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned.strip())


# ══════════════════════════════════════════════════════════════════════════════
# AGREE II CRITERION-TO-SCORE AGGREGATOR
# Converts criterion-level labels from the LLM into numeric item scores using
# a deterministic stepped mapping. The LLM never produces numeric scores —
# this function calculates them from criterion labels only.
# Thresholds calibrated empirically against PD-04 (AAOS Rotator Cuff 2019).
# ══════════════════════════════════════════════════════════════════════════════

_LABEL_WEIGHTS = {
    "fully met":     1.00,
    "mostly met":    0.75,
    "partially met": 0.50,
    "minimally met": 0.25,
    "not met":       0.00,
}

# Criterion keys for each AGREE II item — must match output schema exactly
_AGREE_CRITERIA_KEYS: dict[str, list[str]] = {
    "D1_Objectives_Described":               ["c1", "c2", "c3"],
    "D1_HealthQuestions_Described":          ["c1", "c2", "c3", "c4", "c5"],
    "D1_Population_Described":               ["c1", "c2", "c3", "c4", "c5"],
    "D2_RelevantProfessionals_Included":     ["c1", "c2", "c3", "c4", "c5"],
    "D2_TargetPopViews_Sought":              ["c1", "c2", "c3", "c4"],
    "D2_TargetUsers_Defined":                ["c1", "c2"],
    "D3_SystematicSearch_Used":              ["c1", "c2", "c3", "c4"],
    "D3_SelectionCriteria_Described":        ["c1", "c2"],
    "D3_EvidenceStrengthsLimits_Described":  ["c1", "c2", "c3"],
    "D3_FormulationMethods_Described":       ["c1", "c2", "c3"],
    "D3_BenefitsRisks_Considered":           ["c1", "c2", "c3", "c4"],
    "D3_Link_EvidenceToRecs":                ["c1", "c2", "c3"],
    "D3_ExternalReview_Conducted":           ["c1", "c2", "c3", "c4", "c5"],
    "D3_UpdateProcedure_Provided":           ["c1", "c2", "c3"],
    "D4_Recs_Specific_Unambiguous":          ["c1", "c2", "c3", "c4"],
    "D4_ManagementOptions_Presented":        ["c1", "c2"],
    "D4_KeyRecs_Identifiable":               ["c1", "c2"],
    "D5_BarriersFacilitators_Described":     ["c1", "c2", "c3", "c4"],
    "D5_ApplicationTools_Provided":          ["c1", "c2", "c3"],
    "D5_ResourceImplications_Considered":    ["c1", "c2", "c3", "c4"],
    "D5_MonitoringCriteria_Presented":       ["c1", "c2", "c3"],
    "D6_FundingBody_NoInfluence":            ["c1", "c2"],
    "D6_CompetingInterests_Recorded":        ["c1", "c2", "c3", "c4"],
}

def _stepped_score(proportion: float) -> int:
    """Convert criterion-weight proportion to 1-7 AGREE II score.
    Thresholds empirically calibrated during PD-04 prompt development.
    Score 7 requires all criteria fully met (proportion = 1.0 exactly).
    Any genuine gap, however minor, produces a score of 6 at most."""
    if proportion >= 1.00: return 7
    if proportion >= 0.75: return 6
    if proportion >= 0.55: return 5
    if proportion >= 0.40: return 4
    if proportion >= 0.20: return 3
    if proportion >= 0.10: return 2
    return 1


def score_agree_item(item_key: str, item_data: dict) -> int:
    """Calculate numeric score for one AGREE II item from criterion labels."""
    keys = _AGREE_CRITERIA_KEYS.get(item_key, [])
    if not keys:
        return 1
    weights = []
    for k in keys:
        raw_label = str(item_data.get(k, "not met")).strip().lower()
        weights.append(_LABEL_WEIGHTS.get(raw_label, 0.0))
    proportion = sum(weights) / len(weights) if weights else 0.0
    return _stepped_score(proportion)


def build_agree_scores(raw_agree: dict) -> dict:
    """Convert full AGREE II LLM output to numeric scores + rationales.
    Returns a flat dict with the same keys the app expects downstream."""
    # Explicit mapping from item key to its rationale column key
    _rationale_keys: dict[str, str] = {
        "D1_Objectives_Described":               "D1_Objectives_Rationale",
        "D1_HealthQuestions_Described":          "D1_HealthQuestions_Rationale",
        "D1_Population_Described":               "D1_Population_Rationale",
        "D2_RelevantProfessionals_Included":     "D2_RelevantProfessionals_Rationale",
        "D2_TargetPopViews_Sought":              "D2_TargetPopViews_Rationale",
        "D2_TargetUsers_Defined":                "D2_TargetUsers_Rationale",
        "D3_SystematicSearch_Used":              "D3_SystematicSearch_Rationale",
        "D3_SelectionCriteria_Described":        "D3_SelectionCriteria_Rationale",
        "D3_EvidenceStrengthsLimits_Described":  "D3_EvidenceStrengthsLimits_Rationale",
        "D3_FormulationMethods_Described":       "D3_FormulationMethods_Rationale",
        "D3_BenefitsRisks_Considered":           "D3_BenefitsRisks_Rationale",
        "D3_Link_EvidenceToRecs":                "D3_Link_Rationale",
        "D3_ExternalReview_Conducted":           "D3_ExternalReview_Rationale",
        "D3_UpdateProcedure_Provided":           "D3_UpdateProcedure_Rationale",
        "D4_Recs_Specific_Unambiguous":          "D4_Recs_Specific_Rationale",
        "D4_ManagementOptions_Presented":        "D4_ManagementOptions_Rationale",
        "D4_KeyRecs_Identifiable":               "D4_KeyRecs_Rationale",
        "D5_BarriersFacilitators_Described":     "D5_BarriersFacilitators_Rationale",
        "D5_ApplicationTools_Provided":          "D5_ApplicationTools_Rationale",
        "D5_ResourceImplications_Considered":    "D5_ResourceImplications_Rationale",
        "D5_MonitoringCriteria_Presented":       "D5_MonitoringCriteria_Rationale",
        "D6_FundingBody_NoInfluence":            "D6_FundingBody_Rationale",
        "D6_CompetingInterests_Recorded":        "D6_CompetingInterests_Rationale",
    }
    result = {}
    for item_key, crit_keys in _AGREE_CRITERIA_KEYS.items():
        item_data = raw_agree.get(item_key, {})
        score = score_agree_item(item_key, item_data)
        rationale = item_data.get("rationale", "No rationale provided.")
        # Prepend criterion label summary for transparency in the interface
        label_summary = " | ".join(
            f"{k}: {item_data.get(k, 'not met')}" for k in crit_keys
        )
        result[item_key] = score
        rat_key = _rationale_keys.get(item_key, item_key + "_Rationale")
        result[rat_key] = f"[{label_summary}] {rationale}"
    result["AGREEII_Recommendation"] = raw_agree.get("AGREEII_Recommendation", "")
    return result

_TITLES = {"dr", "prof", "mr", "mrs", "ms", "sir", "dame", "lord", "rev",
           "hon", "a/prof", "assoc", "mx", "miss"}

# Punctuation stripped from candidate tokens before checking / returning
_NAME_STRIP = str.maketrans("", "", ".,;:()")


def extract_first_name(full_name: str) -> str:
    """Return the first non-title given name from a full name string.

    Handles entries like 'Dr Kevin Shea, MD, FAAOS (Oversight Chair)':
    splits on spaces, skips leading title tokens, returns the first
    non-title word with trailing punctuation stripped.
    Preserves apostrophes (O'Connell) and hyphens (Anne-Marie).
    """
    parts = full_name.strip().split()
    for part in parts:
        clean = part.translate(_NAME_STRIP)
        if clean.lower() not in _TITLES and clean:
            return clean
    # Fallback: return first part cleaned of punctuation
    return parts[0].translate(_NAME_STRIP) if parts else full_name


def classify_gender(first_name: str, gender_api_key: str) -> dict:
    """Call GenderAPI.io v1 endpoint. Returns gender (man/woman/unknown) and probability (0-100)."""
    try:
        resp = requests.get(
            "https://api.genderapi.io/api/",
            params={"key": gender_api_key, "name": first_name},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_gender = data.get("gender", "unknown")
        gender_map = {"male": "man", "female": "woman"}
        gender = gender_map.get(str(raw_gender).lower(), "unknown")
        probability = int(data.get("probability", 0))   # 0–100
        return {"gender": gender, "confidence": probability}
    except Exception:
        return {"gender": "unknown", "confidence": 0}


def classify_name_list(names_text: str, gender_api_key: str) -> list[dict]:
    """Classify all names in a semicolon- or newline-separated string.

    Parsing steps for each entry:
      1. Split the full text on semicolons to isolate individual members.
      2. Within each semicolon-chunk, split further on newlines.
      3. Strip leading/trailing whitespace from every token.
      4. Call extract_first_name() to obtain the given name only
         (skipping titles such as Dr, Prof, Mr, Mrs, Ms, Miss).
      5. Pass that given name to the Gender API.
      6. Record the original full entry string in the audit trail.
    """
    entries: list[str] = []
    for chunk in names_text.split(";"):
        for line in chunk.splitlines():
            entry = line.strip()
            _SKIP_VALS = {"not reported", "not available", "none"}
            if entry and entry.lower() not in _SKIP_VALS:
                entries.append(entry)

    results = []
    for name in entries:
        first = extract_first_name(name)
        g = classify_gender(first, gender_api_key)
        results.append({
            "Full name": name,       # original string for audit trail
            "First name used": first,
            "Gender": g["gender"],
            "Confidence": g["confidence"],
        })
        time.sleep(0.15)
    return results


def tally(results: list[dict]) -> tuple[int, int]:
    men   = sum(1 for r in results if r["Gender"] == "man")
    women = sum(1 for r in results if r["Gender"] == "woman")
    return men, women

# ══════════════════════════════════════════════════════════════════════════════
# GENERAL UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def rating_to_idx(value) -> int:
    try:
        r = int(str(value)[0])
        if r in (1, 2, 3):
            return r - 1
    except (ValueError, IndexError):
        pass
    return 0


def option_to_int(opt: str) -> int:
    try:
        return int(opt[0])
    except (ValueError, IndexError):
        return 1


def safe(d: dict, *keys, default: str = "Section not clearly parsed"):
    cur = d
    for k in keys:
        if isinstance(cur, dict):
            cur = cur.get(k)
            if cur is None:
                return default
        else:
            return default
    return cur if cur is not None else default


def list_to_text(val) -> str:
    if isinstance(val, list):
        return "\n".join(str(v) for v in val)
    return str(val) if val is not None else "Not reported"


def sel(label: str, options: list[str], value, **kwargs) -> str:
    v = str(value)
    idx = options.index(v) if v in options else len(options) - 1
    return st.selectbox(label, options, index=idx, **kwargs)


def ev_block(evidence_text: str) -> None:
    """Render a non-editable grey evidence block beneath a Tier 2 field."""
    safe_text = str(evidence_text).replace("<", "&lt;").replace(">", "&gt;")
    st.markdown(
        f'<div class="evidence-block"><strong>AI evidence:</strong> {safe_text}</div>',
        unsafe_allow_html=True,
    )

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════

for _k in ("extracted_text", "file_size", "raw_json", "parsed_data",
           "raw_agree_ii_json", "agree_ii_data",
           "gender_results", "_last_filename", "signoff_timestamp"):
    if _k not in st.session_state:
        st.session_state[_k] = None

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## ⚙️ Settings")

    # ── Anthropic API key ─────────────────────────────────────────────────────
    st.markdown("#### Anthropic API key")
    env_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if env_key:
        api_key: str = env_key
        st.markdown(
            '<div class="box-ok">✓ Anthropic key loaded from environment.</div>',
            unsafe_allow_html=True,
        )
    else:
        api_key = st.text_input(
            "Anthropic API key", type="password", placeholder="sk-ant-…",
            help="Used only for this session; never stored.",
            label_visibility="collapsed",
        )

    st.divider()

    # ── Gender API key ────────────────────────────────────────────────────────
    st.markdown("#### Gender API key")
    env_gender_key = os.getenv("GENDER_API_KEY", "").strip()
    if env_gender_key:
        gender_api_key: str = env_gender_key
        st.markdown(
            '<div class="box-ok">✓ Gender API key loaded from environment.</div>',
            unsafe_allow_html=True,
        )
    else:
        gender_api_key = st.text_input(
            "Gender API key", type="password", placeholder="your-genderapi-key",
            help="Required for committee gender classification. "
                 "Store as GENDER_API_KEY in .env to avoid re-entering.",
            label_visibility="collapsed",
        )
        if gender_api_key:
            st.markdown(
                '<div class="box-ok">✓ Gender API key entered.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="box-warn">⚠️ No Gender API key provided. '
                "Committee gender classification will not be available.</div>",
                unsafe_allow_html=True,
            )

    st.divider()

    # ── PDF parser ────────────────────────────────────────────────────────────
    st.markdown("#### PDF parser")
    parser = st.radio(
        "Extraction engine", ["PyMuPDF (default)", "pdfplumber"],
        label_visibility="collapsed",
    )
    use_pymupdf = parser == "PyMuPDF (default)"

    st.divider()

    # ── Document quality ──────────────────────────────────────────────────────
    st.markdown("#### Document quality")
    if st.session_state.extracted_text and st.session_state.file_size:
        cy = character_yield(st.session_state.extracted_text, st.session_state.file_size)
        _cy_help = (
            "Character yield measures how much text was successfully extracted from the PDF "
            "relative to its file size. A value above 0.1 indicates the document has been parsed "
            "successfully as a text-based PDF. Values below 0.1 suggest the document may be "
            "scanned or image-based and may not extract reliably."
        )
        if cy < 0.1:
            st.markdown(
                f'<div class="box-warn">⚠️ <strong>Low character yield ({cy:.3f})</strong><br>'
                "This document may be scanned or image-based.</div>",
                unsafe_allow_html=True,
            )
        else:
            st.metric("Character yield", f"{cy:.3f}", help=_cy_help)
    else:
        st.caption("Upload a PDF to see quality metrics.")

    st.divider()
    st.caption("CPG Sex & Gender Extraction Tool · Powered by Claude claude-sonnet-4-6")

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("# CPG Sex & Gender Extraction Tool")
st.markdown(
    "Structured data extraction from clinical practice guidelines for systematic review · "
    "Powered by Claude (claude-sonnet-4-6)"
)

# ── PDF upload ────────────────────────────────────────────────────────────────

uploaded = st.file_uploader(
    "Upload a clinical practice guideline PDF", type=["pdf"],
    help="Upload the full PDF of the CPG to be extracted.",
)

if uploaded:
    raw_bytes = uploaded.read()
    st.session_state.file_size = len(raw_bytes)

    if st.session_state["_last_filename"] != uploaded.name:
        st.session_state.raw_json = None
        st.session_state.parsed_data = None
        st.session_state.raw_agree_ii_json = None
        st.session_state.agree_ii_data = None
        st.session_state.gender_results = None
        st.session_state.signoff_timestamp = None
        st.session_state["_last_filename"] = uploaded.name
        for _k in ("t3b_chair", "t3b_clin", "t3b_lay"):
            st.session_state.pop(_k, None)

    with st.spinner("Extracting PDF text…"):
        try:
            text = (
                extract_text_pymupdf(raw_bytes)
                if use_pymupdf
                else extract_text_pdfplumber(raw_bytes)
            )
            st.session_state.extracted_text = text
        except Exception as exc:
            st.error(f"PDF extraction failed: {exc}")
            st.stop()

    cy = character_yield(text, st.session_state.file_size)
    c1, c2, c3 = st.columns(3)
    c1.metric("Characters extracted", f"{len(text):,}")
    c2.metric("File size (bytes)", f"{st.session_state.file_size:,}")
    c3.metric("Character yield", f"{cy:.3f}")

    if cy < 0.1:
        st.markdown(
            '<div class="box-warn">⚠️ <strong>Low character yield detected.</strong> '
            "This document appears to be scanned or image-based. "
            "Consider using an OCR-processed version.</div>",
            unsafe_allow_html=True,
        )
    if len(text) > 500_000:
        st.markdown(
            f'<div class="box-info">ℹ️ Long document (~{len(text)//1000} k characters). '
            "Extraction may take 60–120 seconds.</div>",
            unsafe_allow_html=True,
        )

    with st.expander("Preview extracted text (first 2 000 characters)"):
        st.text(text[:2000])

# ── Extract button ────────────────────────────────────────────────────────────

if st.session_state.extracted_text:
    st.divider()
    bcol, icol = st.columns([2, 5])
    with bcol:
        run = st.button(
            "🔍 Extract structured data", type="primary",
            use_container_width=True, disabled=not api_key,
        )
    with icol:
        if not api_key:
            st.markdown(
                '<div class="box-warn">⚠️ Enter your Anthropic API key in the sidebar.</div>',
                unsafe_allow_html=True,
            )

    if run:
        with st.spinner("Step 1/2 — Running main extraction (Tiers 1–3 + Overall rating)…"):
            try:
                raw = call_claude(
                    api_key, SYSTEM_PROMPT,
                    USER_PROMPT_TEMPLATE.format(text=st.session_state.extracted_text),
                )
                st.session_state.raw_json = raw
                st.session_state.parsed_data = parse_json_response(raw)
                # Override LLM sg_total_mentions with deterministic Python count.
                # The LLM consistently miscounts by including gendered pronouns;
                # the Python counter applies the protocol term list precisely.
                _py_count = count_sg_terms(st.session_state.extracted_text)
                if "tier2" in st.session_state.parsed_data:
                    st.session_state.parsed_data["tier2"]["sg_total_mentions"] = _py_count
            except json.JSONDecodeError as exc:
                st.error(f"Main extraction — Claude returned invalid JSON: {exc}")
                with st.expander("Raw response"):
                    st.code(st.session_state.raw_json or "", language="text")
                st.stop()
            except anthropic.APIError as exc:
                st.error(f"Anthropic API error (main extraction): {exc}")
                st.stop()
            except Exception as exc:
                st.error(f"Unexpected error (main extraction): {exc}")
                st.stop()

        with st.spinner("⏳ Waiting 45 seconds before AGREE II assessment to avoid API rate limits…"):
            for _i in range(45):
                time.sleep(1)

        with st.spinner("Step 2/2 — Running AGREE II quality assessment…"):
            try:
                raw_ag = call_claude(
                    api_key, AGREE_II_SYSTEM_PROMPT,
                    AGREE_II_USER_PROMPT.format(text=st.session_state.extracted_text),
                    max_tokens=6000,
                )
                st.session_state.raw_agree_ii_json = raw_ag
                # Parse criterion labels then convert to numeric scores via
                # deterministic Python aggregation — LLM never assigns scores.
                _raw_agree = parse_json_response(raw_ag)
                st.session_state.agree_ii_data = build_agree_scores(_raw_agree)
            except json.JSONDecodeError as exc:
                st.warning(f"AGREE II — invalid JSON: {exc}. Main extraction results still available.")
                st.session_state.agree_ii_data = {}
            except Exception as exc:
                st.warning(f"AGREE II assessment failed: {exc}. Main extraction results still available.")
                st.session_state.agree_ii_data = {}

        # Reset sign-offs when extraction is re-run
        st.session_state.signoff_timestamp = None
        for _sk in SIGNOFF_KEYS:
            st.session_state[_sk] = False
        for _k in ("t3b_chair", "t3b_clin", "t3b_lay"):
            st.session_state.pop(_k, None)

        st.success("Extraction complete. Review all sections and tick the sign-off boxes before exporting.")

# ══════════════════════════════════════════════════════════════════════════════
# RESULTS
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.parsed_data:
    data: dict = st.session_state.parsed_data
    st.divider()
    st.markdown("## Extraction results")
    st.caption(
        "Review all fields. Tick the sign-off checkbox at the bottom of each section before exporting."
    )

    edits: dict = {}

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 1
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="tier-header">Tier 1 — Descriptive fields</div>', unsafe_allow_html=True)
    t1: dict = data.get("tier1") or {}

    c1, c2 = st.columns(2)
    with c1:
        edits["Guideline title"] = st.text_input(
            "Guideline title", value=str(safe(t1, "guideline_title")))
        edits["Publication year"] = st.text_input(
            "Publication year", value=str(safe(t1, "publication_year")))
        edits["Update year"] = st.text_input(
            "Update year", value=str(safe(t1, "update_year")))
        edits["Country of origin"] = st.text_input(
            "Country of origin", value=str(safe(t1, "country_of_origin")))
    with c2:
        edits["Organisation/Publisher"] = st.text_input(
            "Organisation / Publisher", value=str(safe(t1, "organisation_publisher")))
        edits["Authors"] = st.text_input(
            "Authors", value=str(safe(t1, "authors")))
        _gt_opts = ["CPG", "Clinical care standard", "Guide", "Section not clearly parsed"]
        edits["Guideline type"] = sel("Guideline type", _gt_opts, safe(t1, "guideline_type"))
        edits["Musculoskeletal condition"] = st.text_input(
            "Musculoskeletal condition addressed",
            value=str(safe(t1, "musculoskeletal_condition")))

    # Fix 4: Tier 1 sign-off
    st.checkbox(SIGNOFF_TEXT, key="signoff_tier1")

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 2 — Fix 2: evidence blocks beneath each field
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="tier-header">Tier 2 — Terminology fields</div>', unsafe_allow_html=True)
    t2: dict = data.get("tier2") or {}

    # S/G count + context
    sg_c1, sg_c2 = st.columns([1, 3])
    with sg_c1:
        edits["Total S/G Mentions"] = st.text_input(
            "Total S/G Mentions",
            value=str(safe(t2, "sg_total_mentions", default="0")),
            help="Total count of sex/gender-related term occurrences in the guideline text.",
        )
    with sg_c2:
        edits["Example/Context"] = st.text_area(
            "Example / Context",
            value=str(safe(t2, "sg_example_context", default="NA")),
            height=68,
            help="Brief description of the main contexts in which sex/gender terms appear.",
        )

    # Collect evidence values for display and export
    t2_evidence: dict[str, str] = {
        "Mention_of_SG_Evidence":           str(safe(t2, "mention_of_sex_or_gender_evidence",   default="")),
        "Definitions_Provided_Evidence":    str(safe(t2, "definitions_provided_evidence",        default="")),
        "Overall_Correctness_Evidence":     str(safe(t2, "correct_usage_overall_evidence",       default="")),
        "Nonbinary_Use_Evidence":           str(safe(t2, "nonbinary_use_evidence",               default="")),
        "Appropriate_Categories_Evidence":  str(safe(t2, "appropriate_categories_evidence",      default="")),
        "Non_Interchangeability_Evidence":  str(safe(t2, "non_interchangeability_evidence",      default="")),
    }

    c1, c2 = st.columns(2)
    with c1:
        edits["Mention of sex or gender"] = sel(
            "Mention of sex or gender",
            ["Sex only", "Gender only", "Both", "Neither", "Section not clearly parsed"],
            safe(t2, "mention_of_sex_or_gender"),
        )
        ev_block(t2_evidence["Mention_of_SG_Evidence"])

        edits["Definitions provided"] = sel(
            "Definitions provided",
            ["Yes", "No", "Section not clearly parsed"],
            safe(t2, "definitions_provided"),
        )
        ev_block(t2_evidence["Definitions_Provided_Evidence"])

        edits["Definitions text"] = st.text_area(
            "Definition text (if Yes)", value=str(safe(t2, "definitions_text")), height=80,
        )

        edits["Correct usage overall"] = sel(
            "Correct usage overall rating",
            ["Correct", "Unclear", "Incorrect", "Section not clearly parsed"],
            safe(t2, "correct_usage_overall"),
        )
        ev_block(t2_evidence["Overall_Correctness_Evidence"])

    with c2:
        edits["Nonbinary use criterion"] = sel(
            "Nonbinary use criterion",
            ["Nonbinary", "Binary", "Unclear", "Section not clearly parsed"],
            safe(t2, "nonbinary_use"),
        )
        ev_block(t2_evidence["Nonbinary_Use_Evidence"])

        edits["Appropriate categories criterion"] = sel(
            "Appropriate categories criterion",
            ["Appropriate", "Inappropriate", "Unclear", "Section not clearly parsed"],
            safe(t2, "appropriate_categories"),
        )
        ev_block(t2_evidence["Appropriate_Categories_Evidence"])

        edits["Non-interchangeability criterion"] = sel(
            "Non-interchangeability criterion",
            ["Noninterchangeable", "Interchangeable", "Unclear", "Section not clearly parsed"],
            safe(t2, "non_interchangeability"),
        )
        ev_block(t2_evidence["Non_Interchangeability_Evidence"])

    # Fix 4: Tier 2 sign-off
    st.checkbox(SIGNOFF_TEXT, key="signoff_tier2")

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 3
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="tier-header">Tier 3 — Qualitative judgment fields</div>', unsafe_allow_html=True)
    st.caption("Rating: 1 = No mention · 2 = Superficial mention · 3 = Substantial mention")
    t3: dict = data.get("tier3") or {}

    for fk, fl in TIER3_DOMAINS:
        dom: dict = t3.get(fk) or {}
        st.markdown(f"**{fl}**")
        dc1, dc2 = st.columns([1, 3])
        with dc1:
            edits[f"{fl} — Rating"] = st.selectbox(
                "Rating", RATING_OPTIONS,
                index=rating_to_idx(dom.get("rating", 1)),
                key=f"r_{fk}", label_visibility="collapsed",
            )
        with dc2:
            edits[f"{fl} — Evidence"] = st.text_area(
                "Evidence",
                value=str(dom.get("evidence", "No relevant content identified")),
                height=80, key=f"e_{fk}", label_visibility="collapsed",
            )

    computed_score: int = sum(
        option_to_int(edits.get(f"{fl} — Rating", RATING_OPTIONS[0]))
        for _, fl in TIER3_DOMAINS
    )
    edits["Cumulative domain score"] = computed_score
    ai_score = t3.get("cumulative_domain_score", "?")
    st.markdown(
        f"**Cumulative domain score (auto-calculated):** **{computed_score}** / 27 "
        f"&nbsp;&nbsp;*(AI reported: {ai_score})*",
        unsafe_allow_html=True,
    )

    # Fix 4: Tier 3 sign-off
    st.checkbox(SIGNOFF_TEXT, key="signoff_tier3")

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 3b — resolve early so display always shows current resolved data
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown(
        '<div class="tier-header">Tier 3b — Guideline development committee</div>',
        unsafe_allow_html=True,
    )
    t3b: dict = data.get("tier3b") or {}
    ai_chair   = list_to_text(t3b.get("chair_members",               "Not reported"))
    ai_clinics = list_to_text(t3b.get("clinicians_and_commissioners", "Not reported"))
    ai_lay     = list_to_text(t3b.get("lay_members",                  "Not reported"))

    def resolve_committee(session_key: str, ai_text: str) -> tuple[str, str]:
        manual = st.session_state.get(session_key, "").strip()
        if manual:
            names = "; ".join(n.strip() for n in manual.splitlines() if n.strip())
            return names, "Manually entered — source verified outside PDF"
        cleaned = ai_text.strip().replace("\n", "; ")
        return cleaned if cleaned else "Not reported", "AI extracted"

    final_chair,   src_chair = resolve_committee("man_chair", ai_chair)
    final_clinics, src_clin  = resolve_committee("man_clin",  ai_clinics)
    final_lay,     src_lay   = resolve_committee("man_lay",   ai_lay)

    # Sync Tier 3b editable text areas:
    # - When manual entry exists it overrides any direct edits to the Tier 3b text area.
    # - When no manual entry exists the text area is editable independently; AI extraction
    #   provides the initial value on first render only.
    if st.session_state.get("man_chair", "").strip():
        st.session_state["t3b_chair"] = final_chair.replace("; ", "\n")
    elif "t3b_chair" not in st.session_state:
        st.session_state["t3b_chair"] = ai_chair

    if st.session_state.get("man_clin", "").strip():
        st.session_state["t3b_clin"] = final_clinics.replace("; ", "\n")
    elif "t3b_clin" not in st.session_state:
        st.session_state["t3b_clin"] = ai_clinics

    if st.session_state.get("man_lay", "").strip():
        st.session_state["t3b_lay"] = final_lay.replace("; ", "\n")
    elif "t3b_lay" not in st.session_state:
        st.session_state["t3b_lay"] = ai_lay

    st.caption(
        "Committee names are pre-filled from AI extraction or manual entry — edit directly if needed. "
        "Use **Manual Committee Membership Entry** below to add or correct names. "
        "Gender tallies appear here after running classification."
    )
    _gr_t3b = st.session_state.gender_results or {}
    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        _lbl = "Chair members (manual — editable)" if src_chair != "AI extracted" else "Chair members (AI extracted — editable)"
        st.text_area(_lbl, key="t3b_chair", height=110)
        if "chair" in _gr_t3b:
            _m, _w = tally(_gr_t3b["chair"])
            st.caption(f"👨 Men: **{_m}** · 👩 Women: **{_w}** · Other/Unknown: **{len(_gr_t3b['chair'])-_m-_w}**")
    with bc2:
        _lbl = "Clinicians & commissioners (manual — editable)" if src_clin != "AI extracted" else "Clinicians & commissioners (AI extracted — editable)"
        st.text_area(_lbl, key="t3b_clin", height=110)
        if "clin" in _gr_t3b:
            _m, _w = tally(_gr_t3b["clin"])
            st.caption(f"👨 Men: **{_m}** · 👩 Women: **{_w}** · Other/Unknown: **{len(_gr_t3b['clin'])-_m-_w}**")
    with bc3:
        _lbl = "Lay members (manual — editable)" if src_lay != "AI extracted" else "Lay members (AI extracted — editable)"
        st.text_area(_lbl, key="t3b_lay", height=110)
        if "lay" in _gr_t3b:
            _m, _w = tally(_gr_t3b["lay"])
            st.caption(f"👨 Men: **{_m}** · 👩 Women: **{_w}** · Other/Unknown: **{len(_gr_t3b['lay'])-_m-_w}**")

    # ── Classify committee gender — Tier 3b button ───────────────────────────
    if gender_api_key:
        if st.button("🔍 Classify committee gender", key="classify_gender_t3b"):
            with st.spinner("Classifying names via Gender API…"):
                _new_gr: dict = {}
                for _ckey, _nstr in [
                    ("chair", st.session_state.get("t3b_chair", final_chair)),
                    ("clin",  st.session_state.get("t3b_clin",  final_clinics)),
                    ("lay",   st.session_state.get("t3b_lay",   final_lay)),
                ]:
                    if (_nstr or "").strip().lower() not in {"", "not reported", "not available", "none"}:
                        _new_gr[_ckey] = classify_name_list(_nstr, gender_api_key)
                    else:
                        _new_gr[_ckey] = []
                st.session_state.gender_results = _new_gr
            st.rerun()
    else:
        st.caption("Enter a Gender API key in the sidebar to enable gender classification.")

    # Show classification results in Tier 3b if available
    if st.session_state.gender_results is not None:
        _grt = st.session_state.gender_results
        _tc1, _tc2, _tc3 = st.columns(3)
        for _cw, _ck, _cl in [
            (_tc1, "chair", "Chair members"),
            (_tc2, "clin",  "Clinicians & commissioners"),
            (_tc3, "lay",   "Lay members"),
        ]:
            with _cw:
                _r = _grt.get(_ck, [])
                if _r:
                    _df = pd.DataFrame(_r)
                    _df["Confidence"] = _df["Confidence"].apply(lambda x: f"{int(x)}%")
                    st.dataframe(_df, use_container_width=True, hide_index=True)
                _tm, _tw = tally(_r)
                st.caption(f"👨 Men: **{_tm}** · 👩 Women: **{_tw}** · Other/Unknown: **{len(_r)-_tm-_tw}**")

    # Fix 4: Tier 3b sign-off
    st.checkbox(SIGNOFF_TEXT, key="signoff_tier3b")

    # ══════════════════════════════════════════════════════════════════════════
    # OVERALL RATING
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="tier-header">Overall rating</div>', unsafe_allow_html=True)
    ov: dict = data.get("overall_rating") or {}
    _cat_opts = ["1", "2", "3", "4", "5", "Section not clearly parsed"]
    edits["Overall category"] = sel(
        "Category (1–5)", _cat_opts, str(ov.get("category", "Section not clearly parsed"))
    )
    edits["Overall category rationale"] = st.text_area(
        "Rationale (AI synthesis)",
        value=str(ov.get("rationale", "Section not clearly parsed")),
        height=90,
    )

    with st.expander("Category definitions"):
        st.markdown(
            "**1** Evidence-informed recommendations supporting different or singular approaches for men and women  \n"
            "**2** Sex-specific reference values for laboratory or clinical data  \n"
            "**3** Sex/gender differences in epidemiology or risk factors, without clinical management suggestions  \n"
            "**4** Superficial mention of sex or gender only  \n"
            "**5** No mention of sex or gender"
        )

    # Fix 4: Overall rating sign-off
    st.checkbox(SIGNOFF_TEXT, key="signoff_overall")

    # ══════════════════════════════════════════════════════════════════════════
    # AGREE II
    # ══════════════════════════════════════════════════════════════════════════
    ag = st.session_state.agree_ii_data or {}
    agree_edits: dict = {}

    st.markdown('<div class="tier-header">AGREE II Quality Assessment</div>', unsafe_allow_html=True)
    st.caption(
        "23-item assessment across 6 domains. Rate each item 1 (Strongly Disagree) to 7 (Strongly Agree). "
        "All ratings and rationales are editable. Domain scores are calculated automatically."
    )

    for domain in AGREE_II_DOMAINS:
        st.markdown(f"**{domain['name']}**")

        for col_name, item_text, rationale_col in domain["items"]:
            st.markdown(f"*{item_text}*")
            ai_col, ai_rat = st.columns([1, 3])
            with ai_col:
                agree_edits[col_name] = sel(
                    col_name, AGREE_RATING_OPTIONS,
                    agree_rating_to_option(ag.get(col_name, 4)),
                    key=f"ag_{col_name}",
                )
            with ai_rat:
                _rat_val = str(ag.get(rationale_col, ""))
                agree_edits[rationale_col] = st.text_area(
                    rationale_col, value=_rat_val, height=68,
                    key=f"ag_{rationale_col}", label_visibility="collapsed",
                )
                if not agree_edits[rationale_col].strip():
                    st.markdown(
                        '<div class="box-warn" style="margin-top:-0.5rem;">⚠️ '
                        "Rationale is required — enter at least one sentence.</div>",
                        unsafe_allow_html=True,
                    )

        domain_ratings = [agree_edits.get(c, AGREE_DEFAULT) for c, _, _ in domain["items"]]
        d_score = calc_domain_score(domain_ratings)
        score_icon = "✅" if d_score > 60 else "⚠️"
        st.markdown(
            f"**{domain['name'].split('—')[1].strip()} domain score: {score_icon} {d_score}%**"
        )
        agree_edits[domain["score_col"]] = d_score
        st.markdown("")

    all_domain_scores = [agree_edits[d["score_col"]] for d in AGREE_II_DOMAINS]
    quality_label = overall_quality_label(all_domain_scores)
    agree_edits["AGREEII_Overall_Quality_Rating"] = quality_label

    _qual_css = "box-ok" if quality_label == "High quality" else "box-warn"
    st.markdown(
        f'<div class="{_qual_css}"><strong>Overall AGREE II quality: {quality_label}</strong>'
        f"<br>Based on {sum(1 for s in all_domain_scores if s > 60)} of 6 domains scoring above 60%.</div>",
        unsafe_allow_html=True,
    )

    agree_edits["AGREEII_Recommendation"] = st.text_area(
        "AGREE II Recommendation (AI-generated, editable)",
        value=str(ag.get("AGREEII_Recommendation", "Section not clearly parsed")),
        height=100, key="ag_recommendation",
    )

    # Fix 3: consolidated empty-rationale warning for export awareness
    _empty_rats = [
        rc for dom in AGREE_II_DOMAINS for _, _, rc in dom["items"]
        if not agree_edits.get(rc, "").strip()
    ]
    if _empty_rats:
        st.markdown(
            '<div class="box-warn">⚠️ <strong>Empty rationales detected.</strong> '
            f"The following {len(_empty_rats)} rationale field(s) are blank — please complete "
            "them before signing off: " + ", ".join(_empty_rats) + "</div>",
            unsafe_allow_html=True,
        )

    with st.expander("View raw AGREE II API response (JSON)"):
        st.code(st.session_state.raw_agree_ii_json or "", language="json")

    # Fix 4: AGREE II sign-off
    st.checkbox(SIGNOFF_TEXT, key="signoff_agreeii")

    # ── Parsing quality flags ─────────────────────────────────────────────────
    flagged = [k for k, v in {**edits, **agree_edits}.items()
               if str(v) == "Section not clearly parsed"]
    if flagged:
        st.markdown('<div class="tier-header">⚠️ Parsing quality flags</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="box-warn">The following fields were returned as '
            "<em>Section not clearly parsed</em> and require manual review:</div>",
            unsafe_allow_html=True,
        )
        for f in flagged:
            st.markdown(f"- {f}")

    with st.expander("View raw main extraction API response (JSON)"):
        st.code(st.session_state.raw_json or "", language="json")

    # ══════════════════════════════════════════════════════════════════════════
    # MANUAL COMMITTEE ENTRY
    # ══════════════════════════════════════════════════════════════════════════
    st.divider()
    with st.expander("📝 Manual Committee Membership Entry", expanded=False):
        st.markdown(
            "Use this section to supplement or correct AI-extracted committee member names. "
            "**Enter one name per line.** Manually entered names replace AI-extracted values "
            "in exports and are flagged with an audit trail label."
        )
        st.markdown(
            '<div class="box-info">ℹ️ This section is always available regardless of whether '
            'the AI returned names or "Not reported".</div>',
            unsafe_allow_html=True,
        )
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.text_area("Chair members (manual — one per line)", key="man_chair",
                         placeholder="Prof. Jane Smith\nDr. John Brown", height=160)
        with mc2:
            st.text_area("Clinicians & commissioners (manual — one per line)", key="man_clin",
                         placeholder="Dr. Alice Patel\nMs. Sarah Lee", height=160)
        with mc3:
            st.text_area("Lay members (manual — one per line)", key="man_lay",
                         placeholder="Mr. James Carter\nMrs. Diana Walsh", height=160)

    # ── Gender classification ─────────────────────────────────────────────────
    st.markdown("#### Committee gender classification")

    if gender_api_key:
        if st.button("🔍 Classify committee gender", key="classify_gender"):
            with st.spinner("Classifying names via Gender API…"):
                gr: dict = {}
                for cat_key, names_str in [
                    ("chair", st.session_state.get("t3b_chair", final_chair)),
                    ("clin",  st.session_state.get("t3b_clin",  final_clinics)),
                    ("lay",   st.session_state.get("t3b_lay",   final_lay)),
                ]:
                    if (names_str or "").strip().lower() not in {"", "not reported", "not available", "none"}:
                        # Pass raw text — classify_name_list splits on ; and \n internally
                        gr[cat_key] = classify_name_list(names_str, gender_api_key)
                    else:
                        gr[cat_key] = []
                st.session_state.gender_results = gr
    else:
        st.caption("Enter a Gender API key in the sidebar to enable gender classification.")

    gr = st.session_state.gender_results or {}
    chair_men = chair_women = clin_men = clin_women = lay_men = lay_women = 0

    if gr:
        gc1, gc2, gc3 = st.columns(3)
        for col_widget, cat_key, label in [
            (gc1, "chair", "Chair members"),
            (gc2, "clin",  "Clinicians & commissioners"),
            (gc3, "lay",   "Lay members"),
        ]:
            with col_widget:
                st.markdown(f"**{label}**")
                results = gr.get(cat_key, [])
                if results:
                    df_g = pd.DataFrame(results)
                    df_g["Confidence"] = df_g["Confidence"].apply(lambda x: f"{int(x)}%")
                    st.dataframe(df_g, use_container_width=True, hide_index=True)
                m, w = tally(results)
                st.caption(f"👨 Men: **{m}** · 👩 Women: **{w}** · Other/Unknown: **{len(results)-m-w}**")
                if cat_key == "chair":
                    chair_men, chair_women = m, w
                elif cat_key == "clin":
                    clin_men,  clin_women  = m, w
                else:
                    lay_men,   lay_women   = m, w

    # ══════════════════════════════════════════════════════════════════════════
    # Fix 4: SIGN-OFF GATING + TIMESTAMP
    # ══════════════════════════════════════════════════════════════════════════

    _all_signed = all(st.session_state.get(k, False) for k in SIGNOFF_KEYS)

    # Record timestamp when all sign-offs become complete for the first time
    if _all_signed and st.session_state.signoff_timestamp is None:
        st.session_state.signoff_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif not _all_signed:
        st.session_state.signoff_timestamp = None

    # ══════════════════════════════════════════════════════════════════════════
    # EXPORT
    # ══════════════════════════════════════════════════════════════════════════
    st.divider()
    st.markdown("### Export results")

    def build_row() -> dict:
        row: dict = {}

        # Tier 1
        for k in [
            "Guideline title", "Publication year", "Update year", "Country of origin",
            "Organisation/Publisher", "Authors", "Guideline type", "Musculoskeletal condition",
        ]:
            row[k] = edits.get(k, "")

        # Tier 2 — S/G counts + existing rating fields
        row["Total S/G Mentions"] = edits.get("Total S/G Mentions", "")
        row["Example/Context"]    = edits.get("Example/Context", "")
        for k in [
            "Mention of sex or gender", "Definitions provided", "Definitions text",
            "Correct usage overall", "Nonbinary use criterion",
            "Appropriate categories criterion", "Non-interchangeability criterion",
        ]:
            row[k] = edits.get(k, "")

        # Fix 2: Tier 2 evidence columns
        for col_name, ev_val in t2_evidence.items():
            row[col_name] = ev_val

        # Tier 3
        for _, fl in TIER3_DOMAINS:
            row[f"{fl} — Rating"]   = option_to_int(edits.get(f"{fl} — Rating", RATING_OPTIONS[0]))
            row[f"{fl} — Evidence"] = edits.get(f"{fl} — Evidence", "")
        row["Cumulative domain score"] = computed_score

        # Tier 3b with audit trail + gender tallies
        # Use the editable Tier 3b text area values as the authoritative export source
        row["Chair members"]                         = st.session_state.get("t3b_chair", final_chair).replace("\n", "; ")
        row["Chair members — Source"]                = src_chair
        row["Chair — Men-associated Names"]          = chair_men if gr else ""
        row["Chair — Women-associated Names"]        = chair_women if gr else ""
        row["Clinicians and commissioners"]          = st.session_state.get("t3b_clin", final_clinics).replace("\n", "; ")
        row["Clinicians and commissioners — Source"] = src_clin
        row["Clinicians — Men-associated Names"]     = clin_men if gr else ""
        row["Clinicians — Women-associated Names"]   = clin_women if gr else ""
        row["Lay members"]                           = st.session_state.get("t3b_lay", final_lay).replace("\n", "; ")
        row["Lay members — Source"]                  = src_lay
        row["Lay members — Men-associated Names"]    = lay_men if gr else ""
        row["Lay members — Women-associated Names"]  = lay_women if gr else ""

        # Overall rating
        row["Overall category"]           = edits.get("Overall category", "")
        row["Overall category rationale"] = edits.get("Overall category rationale", "")

        # AGREE II — item scores exported as integers (1–7), rationales as text
        for domain in AGREE_II_DOMAINS:
            for col_name, _, rationale_col in domain["items"]:
                row[col_name]      = agree_item_score(agree_edits.get(col_name, AGREE_DEFAULT))
                row[rationale_col] = agree_edits.get(rationale_col, "")
            row[domain["score_col"]] = agree_edits.get(domain["score_col"], "")
        row["AGREEII_Overall_Quality_Rating"] = agree_edits.get("AGREEII_Overall_Quality_Rating", "")
        row["AGREEII_Recommendation"]         = agree_edits.get("AGREEII_Recommendation", "")

        # Fix 4: reviewer sign-off metadata
        row["Reviewer_Signoff_Complete"] = _all_signed
        row["Signoff_Timestamp"]         = st.session_state.signoff_timestamp or ""

        return row

    if not _all_signed:
        # How many remain?
        _remaining = sum(1 for k in SIGNOFF_KEYS if not st.session_state.get(k, False))
        st.markdown(
            f'<div class="box-warn">⚠️ <strong>Please complete all section reviews before exporting.</strong><br>'
            f"{_remaining} of {len(SIGNOFF_KEYS)} section sign-off(s) still outstanding. "
            "Tick the checkbox at the bottom of each section above.</div>",
            unsafe_allow_html=True,
        )
    else:
        # All signed off — check for empty AGREE II rationales as a final warning
        if _empty_rats:
            st.markdown(
                '<div class="box-warn">⚠️ <strong>Warning:</strong> '
                f"{len(_empty_rats)} AGREE II rationale field(s) are still blank. "
                "Export will proceed but those fields will be empty in the file.</div>",
                unsafe_allow_html=True,
            )

        export_df = pd.DataFrame([build_row()])

        ec1, ec2, _ = st.columns([1, 1, 4])

        with ec1:
            csv_data = export_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇️ Download CSV", data=csv_data,
                file_name="cpg_extraction.csv", mime="text/csv",
                use_container_width=True,
            )

        with ec2:
            xlsx_buf = io.BytesIO()
            with pd.ExcelWriter(xlsx_buf, engine="openpyxl") as writer:
                export_df.to_excel(writer, index=False, sheet_name="Extraction")
                ws = writer.sheets["Extraction"]
                for col_cells in ws.columns:
                    max_w = max(len(str(c.value or "")) for c in col_cells)
                    ws.column_dimensions[col_cells[0].column_letter].width = min(max_w + 4, 60)
            xlsx_buf.seek(0)
            st.download_button(
                "⬇️ Download Excel", data=xlsx_buf,
                file_name="cpg_extraction.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        st.caption(
            f"Signed off at {st.session_state.signoff_timestamp}. "
            "Export includes all fields, AGREE II assessment, gender tallies, and reviewer sign-off metadata."
        )
