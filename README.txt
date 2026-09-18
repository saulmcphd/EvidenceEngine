========================================================================
PROJECT: EvidenceEngine: AI-Assisted Systematic Review Pipeline
ROOT FOLDER: Systematic Reviews
COMPLIANCE: Cochrane Handbook & the proposed PRISMA-trAIce reporting extension (not yet endorsed)

========================================================================

1. OVERVIEW
-----------
EvidenceEngine provides a standardized, reproducible pipeline for acting 
as an Automated Independent Second Reviewer. It utilizes frontier Large 
Language Models (LLMs) to perform expert data extraction, Risk of Bias 
audits, and Results Synthesis in a single pass, ensuring scientific 
transparency and "Meaningful Human Control" for evidence synthesis.

2. FOLDER STRUCTURE
-------------------
Systematic Reviews/
├── prompter.py          - THE ENGINE: Multiprocessing script for AI extraction.
├── promptfile.txt       - THE BRAIN: Universal PICO, RoB, and Results prompt.
├── requirements.txt     - THE DEPENDENCIES: Lists required Python libraries.
├── .env                 - THE KEYS: Private API keys (DO NOT SHARE).
├── .gitignore           - THE FILTER: Prevents private keys from being uploaded.
├── README.txt           - THE GUIDE: (This file).
├── PDFs/                - INPUT: Place all full-text academic papers here.
└── Outputs/             - RESULTS: Saves the Master Dataset (Excel), the Vertical Reconciliation file for human audit (CSV), and the    
                            Technical Extraction Log (TXT).

3. INSTALLATION & SETUP (Do this once)
-----------------------
Step 1: Save the 'Systematic Reviews' folder to your 'Documents' folder.

Step 2: Setting Up the Analysis Environment

To run the AI extraction, your computer needs specific "bridges" (libraries) to talk to the AI models and read PDF files. Follow these simple steps:

Open the Project Folder: Locate your Systematic Reviews folder in Windows File Explorer.

Open the Terminal (The easy way):

Click in the Address Bar at the top of the folder window (where it says C:\Users\...).

Type the three letters cmd and press Enter.

A black window (the terminal) will open, already set to your project location.

Install the Bridges:

Copy and paste the following line into the terminal and press Enter:

        pip install -r requirements.txt

Wait for the process to finish (you will see "Successfully installed"). You only need to do this once on your computer.

Step 3: Add your secret API keys to the '.env' file.

4. OPERATING PROCEDURE
----------------------
1. Select AI Reviewer: Open 'prompter.py' and scroll to the 'Configuration 
   Area'. Set your 'CHOSEN_PROVIDER' (e.g., anthropic) and 'CHOSEN_MODEL' 
   (e.g., claude-3-5-sonnet-20241022). This ensures your audit trail 
   reflects the exact version used for the review.

2. Define Research Criteria: Edit 'promptfile.txt' to define your 
   specific PICO/PECO, Risk of Bias domains, and Result Categories. 
   Detailed, well-defined variable descriptions improve extraction
   accuracy — be specific about each variable. (If you state a numeric
   figure for the improvement, cite its source.)

3. Execute Pipeline: In the terminal, type: python prompter.py 
   The engine will now process all PDFs in the 'PDFs/' folder using 
   your chosen AI model.

4. Locate Your Findings: Open the Outputs/ folder. Every run generates three timestamped files:

4.1 Master Dataset (Research_Data_...xlsx): The wide-format spreadsheet containing all raw AI results.

4.2 Audit File (Audit_Ready_...csv): This is the vertical list used for the Step 5 Reconciliation Workflow.

4.3 Extraction Log (Extraction_Log_...txt): A technical summary showing which PDFs were successful and which failed.

5. RECONCILIATION WORKFLOW (Scientific Consensus)

========================================================================

1. Open the Audit File: Open the Audit_Ready_Research_Data_...csv file in Excel.

2. Side-by-Side Audit: Compare the AI_Extracted_Value column against the source PDF. Enter your verified findings in the Manual_Value column.

3. Conflict Adjudication: If you disagree with the AI, mark Match? (Y/N) as N. Go back to the PDF to find the "Gold Standard" value.

4. Error Categorization: If the AI failed, label it in the Error_Category column:

 - Numerical: Wrong numbers or decimal errors.

  - Mismatch: Correct data in the wrong category.

 - Confabulation: AI "made up" a value not in the text.

5. Consensus Dataset: Enter the final, verified answer in the Consensus_Value column. This is the only data that will be used for the final paper.

6. Performance Metrics (F1 Score Calculation): To follow the proposed PRISMA-trAIce reporting extension (not yet endorsed), you must calculate the AI’s performance once the audit is finished.

7. Technical Archiving: Save this completed file. It serves as our transparent audit trail for peer review to prove we maintained "Meaningful Human Control."


6. COCHRANE & METHODOLOGICAL ALIGNMENT
---------------------------------------
EvidenceEngine is designed to SUPPORT compliance with the MECIR
(Methodological Expectations of Cochrane Intervention Reviews) standards.
It is an assistant to the reviewer, NOT a replacement for one: the Cochrane
Handbook (Chapter 5, Section 5.5.9) states that automation cannot currently
substitute for a human data extractor.

* Standard C43 (Using data collection forms — Mandatory):
  'promptfile.txt' and 'criteria.txt' act as standardized, version-controlled
  data collection forms. NOTE: C43 requires the form to be PILOTED — pilot
  your prompt on a few studies before a full run.

* Standard C44 (Describing studies — Mandatory):
  Pre-configured prompts capture the study characteristics needed to populate
  the Cochrane "Characteristics of included studies" table (PICO/PECO,
  setting, study design, and Risk of Bias).

* Standards C45/C46 (Extracting data in duplicate —
  C45 study characteristics [Highly desirable]; C46 outcome data [Mandatory]):
  These require AT LEAST TWO PEOPLE working independently. EvidenceEngine does
  NOT, by itself, satisfy them — the AI is a second CHECK, not a second PERSON.
  It performs a first-pass extraction that a human reviewer then independently
  verifies and reconciles (the Reconciliation Workflow above), SUPPORTING but
  not replacing the two-independent-reviewer requirement. For a fully MECIR-
  compliant review, retain a human second extractor; for the strongest
  validation of the AI's accuracy, have the human extract BLIND to the AI and
  then compare. (Dual-independent SCREENING is governed by the study-selection
  standards, not C45/C46.)

* PRISMA-trAIce (proposed checklist; JMIR AI, 2025):
  Every run logs the timestamp, model name + version, and full prompt, so AI
  use is transparent and auditable. PRISMA-trAIce is a PROPOSED reporting
  checklist for AI in evidence synthesis (not yet a formally endorsed
  guideline); EvidenceEngine records what it asks for.


How to Cite:
Mcleod, S.A. (2026). EvidenceEngine: An AI-Assisted Systematic Review
Pipeline for Data Extraction. GitHub. DOI: [Insert Zenodo DOI here].