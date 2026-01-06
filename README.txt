========================================================================
PROJECT: EvidenceEngine: AI-Assisted Systematic Review Pipeline for Data Extraction
ROOT FOLDER: Systematic Reviews
COMPLIANCE: Cochrane Handbook (MECIR Standards) & PRISMA-trAIce (2026)

========================================================================

1. OVERVIEW
-----------
EvidenceEngine provides a standardized, reproducible Human-in-the-Loop pipeline for acting as an Automated Independent Second Reviewer. While it utilizes frontier Large Language Models (LLMs) to perform expert data extraction, Risk of Bias audits, and Results Synthesis, the system is designed to augment—not replace—human expertise.

By generating side-by-side reconciliation logs for every AI decision, the engine ensures 100% manual verification of all findings. This hybrid approach guarantees rigorous scientific transparency and maintains "Meaningful Human Control" over the final evidence synthesis, meeting the highest 2026 standards for AI-assisted systematic reviews.

2. FOLDER STRUCTURE
-------------------
Root folder (name this after your specific review)
├── prompter.py             - THE ENGINE: Multiprocessing script for AI extraction.
├── promptfile.txt          - THE BRAIN: Universal PICO, RoB, and Results prompt.
├── requirements.txt        - THE DEPENDENCIES: Lists required Python libraries.
├── env.template           - THE KEYS: Private API keys (DO NOT SHARE).
├── CITATION.cff            - How to cite the software.
├── Data-Reconciliation.doc - Reconciliation workflow steps.
├── LICENSE                 - The MIT License file.
├── .gitignore               THE FILTER: Prevents private keys from being uploaded.
├── README.txt             - THE GUIDE: (This file).
├── PDFs/                  - INPUT: Place all full-text academic papers here.
└── Outputs/               - RESULTS: Saves the Master Dataset (Excel), the Vertical Reconciliation file for human audit (CSV), and the    
                              Technical Extraction Log (TXT).

3. INSTALLATION & SETUP (Do this once)
-----------------------
Step 1: Create a new folder on your computer and name it according to your specific research project (e.g., "Anxiety_Review_2026"). Move all EvidenceEngine files into this folder.

Step 2: Setting Up the Analysis Environment

To run the AI extraction, your computer needs specific "bridges" (libraries) to talk to the AI models and read PDF files. Follow these simple steps:

Open the Project Folder: Locate your root folder in Windows File Explorer.

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
   Detailed variable descriptions here increase extraction accuracy 
   by up to 16%.

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

6. Performance Metrics (F1 Score Calculation): To satisfy PRISMA-trAIce reporting standards, you must calculate the AI’s performance once the audit is finished.

7. Technical Archiving: Save this completed file. It serves as our transparent audit trail for peer review to prove we maintained "Meaningful Human Control."

6. COCHRANE & METHODOLOGICAL COMPLIANCE
---------------------------------------
This engine is architected to satisfy the **MECIR (Methodological 
Expectations of Cochrane Intervention Reviews)** standards:

* Standard C43 (Structured Forms): The 'promptfile.txt' and 'criteria.txt' 
  serve as digital standardized data collection forms, ensuring 
  unbiased and consistent extraction across all studies.
  
* Standards C45/C46 (Independent Dual Processing): The script acts as the 
  Independent Second Reviewer. The reconciliation workflow allows the 
  primary researcher to independently verify AI decisions, fulfilling the 
  requirement for dual-independent screening and extraction.

* Standard C44 (Detail Requirements): Pre-configured prompts ensure the 
  capture of mandatory "Characteristics of Included Studies" (PICO, 
  settings, study design, and Risk of Bias) required for Cochrane 
  Evidence Tables.

* PRISMA-trAIce (2026): Every run generates a technical log (timestamp, 
  model version, and full prompt), ensuring the AI's "logic" is fully 
  auditable and transparent for peer review.

7. LICENSE
========================================================================
This project is licensed under the MIT License. You are free to use, 
modify, and distribute this software for academic and commercial 
purposes, provided that the original copyright notice and permission 
notice are included in all copies or substantial portions of the 
software. See the 'LICENSE' file for the full text.


How to Cite:
Mcleod, S.A. (2026). EvidenceEngine: AI-Assisted Systematic Review 
Pipeline for Data Extraction. Zenodo. https://doi.org/10.5281/zenodo.18165158
GitHub: https://github.com/saulmcphd/EvidenceEngine