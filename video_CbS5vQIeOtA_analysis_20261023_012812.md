This webinar, featuring experts from Duke Health, MedStar Health, and the Institute for Healthcare Improvement, provides first-hand guidance for managing clinical AI risks.

### **1. Deployment Oversight & Organizational Structure**
Experts recommend a three-tiered oversight structure to ensure accountability and avoid conflicts of interest.
*   **The Governance Body:** Responsible for setting the overall structure, tools, and policies.
*   **The Deployment Team:** Charged with the safe rollout. This must include a **Business Owner/Champion** (clinical workflow expert) and a **Technology Owner** (technical expert).
*   **The Governance Team:** A subset of the governance body that provides oversight. **Guidance:** Christina Silcox notes it is critical to "**avoid overlap with the deployment team**" to ensure objective oversight.
*   **Pre-Deployment Vetting:** Organizations should use a **"staged, risk-based review"** process. 
    *   **Low Risk:** Use an expedited pathway.
    *   **High Risk:** Conduct rigorous review including inspection of underlying data and retrospective testing against local datasets.

### **2. Human Review & "Human-in-the-Loop" (Clinical Conclusions)**
The panelists provided a stark warning regarding the limitations of human oversight in AI workflows.
*   **Vigilance Fatigue:** Raj Ratwani shared a clinical study on AI-drafted patient portal messages where **"75% of the physicians missed [AI] errors."** 
*   **The "Editing" Burden:** Shannon Robinson concluded that AI often creates a **"two to three times lift"** in mental processing for clinicians because they must transition from drafting notes to editing them, which requires a different type of cognitive effort.
*   **Conclusion:** Panellists agreed that **"human in the loop" is a "weak solution"** if used as the sole safety catch for high-frequency tasks.

### **3. Monitoring & Performance Tracking**
Guidance emphasizes that AI safety is a lifecycle commitment, not a one-time check.
*   **Systematic vs. One-off Errors:** Nicoleta Economou highlights that while human errors are often "one-off," AI can introduce **"systematic errors at scale"** that repeat across thousands of patients before being recognized.
*   **Drift Monitoring:** Guidance recommends post-deployment tools to detect **"algorithmic drift"** (performance decay over time).
*   **Centralized Inventory:** Organizations must maintain a **"centralized, searchable inventory"** of all clinical AI tools. 
*   **Sunsetting:** Lee Fleisher recommends establishing clear protocols for when an algorithm should be **"sunsetted"** because it no longer meets safety standards.

### **4. Incident Response & Reporting**
Current reporting systems (like the FDA’s MAUDE database) are often insufficient for software-based AI.
*   **EHR Integration:** Guidance suggests building a **"thumbs up/thumbs down"** or a simple flag directly into the EHR workflow. This allows users to report an "off" or "weird" AI output with one click.
*   **Root Cause Analysis (RCA):** When a safety event occurs, clinical reviewers should work with technology owners to perform an RCA that specifically assesses the AI’s contribution to the failure.
*   **The "AI PSO":** Lee Fleisher recommended the creation of an **"AI Patient Safety Organization (PSO)"** with more "teeth" than existing voluntary systems to protect shared learning from legal discovery.

### **5. Staged Rollout & Change Management**
*   **Local Validation:** Before wide deployment, organizations must conduct **"local validation"** to ensure the model performs on their specific patient population.
*   **Education as Mitigation:** Training should not just be on "how to use" the tool, but on **"competency expectations"** regarding the tool's known limitations.
*   **Staged Patching:** Organizations should treat AI updates like medical device patches (e.g., Stryker devices or smartphone security patches), ensuring every instance of the tool on the network is updated simultaneously.

### **6. Legal & Regulatory Conclusions**
*   **Liability Shift:** Lee Fleisher noted that current contracts often include **"hold harmless"** clauses for vendors, shifting 100% of the liability to the healthcare provider. 
*   **Legal Shielding:** He recommended that systems leverage the **"Quality Assurance and Quality Improvement (QA/QI)"** protections under the **Conditions of Participation (COPs)** as a regulatory lever to protect safety evaluations from litigation.
*   **Patient Perspective:** Patricia McGaffigan noted that patients define "harm" more broadly than clinicians, including **"psychological, emotional, and financial harm"** resulting from AI decisions.

### **Named Frameworks & Numbers**
*   **12-Questionnaire Framework:** Used by Bryan Health to assess AI through the lenses of quality, legal, and analytics.
*   **3 to 15 Errors:** The number of errors observed per patient encounter in certain ambient scribe AI evaluations (Raj Ratwani).
*   **Primary, Secondary, Tertiary Model:** MedStar’s model for tiered risk assessment.
*   **National Radiology Data Registry:** Cited as a successful example of outcome registries that could be emulated for AI.
*   **Make America AI Ready:** A new Department of Labor education module mentioned by Christina Silcox.