# CPG Selection Log
## MSK CPG Gender Review — AI Extraction Tool Development

**Date documented:** 15 May 2026  
**Protocol version:** MSK CPG Gender Review App Development Protocol v1, 19.03.2026  
**OSF pre-registration (methodology study):** https://osf.io/sxnu4  
**OSF pre-registration (parent review):** https://doi.org/10.17605/OSF.IO/2ZEQM  
**GitHub repository:** https://github.com/DrAlessInMotion/msk-cpg-extraction-tool  

---

## Purpose of This Document

This log records the a priori selection of CPGs for the prompt development phase and pilot testing phase of the AI extraction tool, prior to any prompt engineering or application development activity. These selections are documented here as a pre-specified record to prevent data leakage, in accordance with the methodology protocol and TRIPOD-LLM item 9a.

All CPGs listed below are permanently excluded from the formal validation sample (n=30). Following completion of the main review, they will be processed using the finalised tool as part of the full corpus extraction.

---

## Total Corpus

- **Total included CPGs:** 221
- **Eligible for validation sampling** (after exclusions below): 206

---

## Prompt Development CPGs (n=5)

Selected via purposive stratified sampling to maximise heterogeneity across country of origin, issuing organisation, musculoskeletal condition, and anticipated level of sex/gender content. These five CPGs will be used exclusively for iterative prompt engineering and will be excluded from pilot testing and formal validation.

| ID | Guideline Title | Source / Organisation | Country | Body Area / Condition | Rationale for Selection |
|----|----------------|----------------------|---------|----------------------|------------------------|
| PD-01 | NICE Low back pain and sciatica in over 16s: assessment and management (NG59) | NICE | UK | Spine / Pelvis | Large, comprehensive NICE CPG; representative of the dominant source in corpus (48%); anticipated moderate sex/gender content |
| PD-02 | 2021 Clinical Practice Guideline for the Management of Osteoarthritis of the Knee | American Academy of Orthopaedic Surgeons (AAOS) | US | Knee | Major US surgical CPG; structured AAOS format; anticipated low sex/gender content; tests extraction in a format with dense author lists |
| PD-03 | Guideline for the management of knee and hip osteoarthritis (2nd edition) | Royal Australian College of General Practitioners (RACGP) | Australia | Knee / Hip | Australian source (underrepresented in corpus); general practice orientation; different format to NICE/AAOS |
| PD-04 | 2019 Clinical Practice Guideline on the Management of Rotator Cuff Injuries | American Academy of Orthopaedic Surgeons (AAOS) | US | Shoulder / Upper Limb | Shoulder CPG from same organisation as PD-02; tests prompt consistency across two differently-structured documents from the same source; anticipated low–moderate sex/gender content |
| PD-05 | Polymyalgia rheumatica | British Society for Rheumatology (BSR) | UK | Inflammatory / Systemic | Non-NICE UK source; genuinely inflammatory condition; female-skewed epidemiology means anticipated high sex/gender content — useful edge case for prompt development |

**Stratification summary:**
- Countries: UK (×2), US (×2), Australia (×1)
- Organisations: NICE, AAOS (×2), RACGP, BSR
- Body areas: Spine (×1), Knee/Hip (×2), Shoulder (×1), Inflammatory (×1)
- Anticipated sex/gender content: Low–Moderate (×2), Moderate (×2), High (×1)

---

## Pilot Testing CPGs (n=10)

Selected to be distinct from the prompt development set and to maximise heterogeneity in document format, organisation, country, condition, and anticipated sex/gender content. Includes two short procedural NICE guidance documents to test parser performance and prompt handling of near-zero sex/gender content. These CPGs will be excluded from the formal validation sample.

| ID | Guideline Title | Source / Organisation | Country | Body Area / Condition | Rationale for Selection |
|----|----------------|----------------------|---------|----------------------|------------------------|
| PT-01 | NICE Percutaneous interlaminar endoscopic lumbar discectomy for sciatica | NICE | UK | Spine / Pelvis | Short procedural NICE guidance; tests parser on a brief technical document format; anticipated Category 5 — stress-tests graceful handling of near-zero sex/gender content |
| PT-02 | NICE Single-step scaffold insertion for repairing symptomatic chondral knee defects | NICE | UK | Knee | Short procedural NICE guidance; different procedure type and body area to PT-01; tests parser on a second brief technical document |
| PT-03 | 2022 Clinical Practice Guideline for the Management of Anterior Cruciate Ligament Injuries | American Academy of Orthopaedic Surgeons (AAOS) | US | Knee | AAOS format; ACL injury has well-documented sex differences — tests Tier 3 extraction for a condition with meaningful sex/gender content |
| PT-04 | Rheumatoid Arthritis | American College of Rheumatology (ACR) | US | Inflammatory / Systemic | Different US organisation and format to AAOS; high sex/gender relevance for an inflammatory condition |
| PT-05 | APTA Academy of Orthopaedic Physical Therapy: Neck Pain: Revision 2017 | American Physical Therapy Association (APTA) | US | Spine / Pelvis | Allied health CPG format; tests a distinct US document style not represented in the prompt development set |
| PT-06 | Axial spondyloarthritis | British Society for Rheumatology (BSR) | UK | Inflammatory / Systemic | Non-NICE UK format; male-skewed condition — tests prompt handling of low sex/gender content in an inflammatory CPG |
| PT-07 | Management of osteoporosis and the prevention of fragility fractures | Scottish Intercollegiate Guidelines Network (SIGN) | UK | Bone / Joint Health | Scottish guideline with a distinct SIGN format; osteoporosis has very high sex/gender relevance — anticipated Category 1–2 |
| PT-08 | Osteoporosis prevention, diagnosis and management in postmenopausal women and men over 50 years of age | Royal Australian College of General Practitioners (RACGP) | Australia | Bone / Joint Health | Australian format; same condition as PT-07 — enables cross-format consistency check for a high sex/gender content condition |
| PT-09 | WHO guideline for non-surgical management of chronic primary low back pain in adults in primary and community care settings | World Health Organisation (WHO) | International | Spine / Pelvis | Only WHO guideline in corpus; internationally distinct format and scope; tests extraction from a global health document |
| PT-10 | Best Practices for Chiropractic Management of Adult Patients With Mechanical Low Back Pain | Clinical Compass | US | Spine / Pelvis | Chiropractic guideline — non-standard document format not represented elsewhere; same condition as PT-09 to test cross-format consistency |

**Stratification summary:**
- Countries/jurisdictions: UK (×3), US (×4), Australia (×1), International (×1)
- Organisations: NICE (×2), AAOS, ACR, APTA, BSR, SIGN, RACGP, WHO, Clinical Compass
- Body areas: Spine (×4), Knee (×2), Inflammatory (×2), Bone/Joint Health (×2)
- Document format types: Short procedural guidance (×2), full CPG (×8)
- Anticipated sex/gender content: Very low/Category 5 (×2), Low (×1), Moderate (×3), High (×2), Very high (×2)

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 15 May 2026 | Alessandra Marcelo | Initial document — prompt development set (n=5) and pilot testing set (n=10) recorded prior to any prompt engineering or application development activity |

---

*Commit this document to the GitHub repository with the message: "Pre-specify prompt development and pilot CPG sets prior to tool development (TRIPOD-LLM item 9a)"*
