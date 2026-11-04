# INN Digital Infrastructure Strategy (2026 revision)

Institute for Neuroscience and Neurotechnology (INN), Research Computing Group (RCG), Simon Fraser
University (SFU). Updated draft, September 24, 2026. Revision of the strategy dated June 19, 2025; draft prepared by
Patrick Mahon.

<ins>Underlined text</ins> is new or changed since the June 19, 2025 strategy. <mark>Highlighted
text</mark>, and passages headed "Proposal, not yet agreed", are proposals for discussion.

Every section has a fixed anchor: section 2.4 is [`#s2-4`](#s2-4). The decision registry and its
map link here. This page is generated from the strategy's LaTeX source, which isn't in this
repository; change that and regenerate (`tools/strategy_md.py`), not this page.

## <a id="s1"></a>1 Introduction

The Institute for Neuroscience and Neurotechnology (INN) at Simon Fraser University (SFU) proposes the development of a modular digital infrastructure for research. This ecosystem aims to support the full cycle of neuroscience research, including pre-planning, data collection, analysis, collaboration, sharing, and iteration, while handling large, heterogeneous, and sometimes sensitive datasets. Leveraging the Digital Research Alliance infrastructure, this platform will provide modular interaction with various stages of scientific projects and integrate seamlessly with external digital services.

> *New since June 2025.*
>
> This revision grounds the strategy in INN’s Mission and Values (Section [2.2](#s2-2)) ([Institute for Neuroscience and Neurotechnology, n.d.c](#ref-innvalues)). The infrastructure serves INN’s research goals, including computational modelling and neuro-AI, which place particular demands on sensitive-data handling and compute. INN’s value of Accessible and Open Research is what drives its open-science work; the SFU Open Science and Open Scholarship Principles are the institutional framework through which INN practises it ([Simon Fraser University 2025](#ref-sfuos)), so that research outputs are “as open as possible and as closed as necessary” ([European Commission, Directorate-General for Research & Innovation 2016](#ref-ec2016fair)). Where an easier implementation would repeat errors the field has already documented, the strategy deliberately takes the harder path (Section [2.7](#s2-7)).
>
> INN led the development of SFU’s Open Scholarship Framework ([Simon Fraser University, n.d.b](#ref-sfuosframework); [SFU News 2025](#ref-sfunews2025)), through the INN-led Open Science Buy-In Project ([Institute for Neuroscience and Neurotechnology, n.d.b](#ref-innbuyin)) and in partnership with the Tanenbaum Open Science Institute ([Institute for Neuroscience and Neurotechnology, n.d.a](#ref-innopenscience); [The Neuro, McGill University, n.d.](#ref-tosi)), which established institution-wide open science at the Montreal Neurological Institute ([Poupon, Seyller, and Rouleau 2017](#ref-poupon2017tosi)). The university-wide Open Scholarship initiative is INN’s partner for community engagement, building buy-in and culture change across SFU. Technical implementation, and this strategy, are scoped to INN.
>
> **Planning horizon.** INN plans at two horizons: a five-year strategic plan, and an annual operating plan that sets what is implemented each year. This strategy sits with the first. It sets out the design principles and the direction of travel, and how they align with INN’s mission and strategic plan. It does not commit INN to specific tools or solutions in advance. Tools named here are examples of a category, not selections. What is built, and when, is decided each year in INN’s operating plan.

## <a id="s2"></a>2 Context

### <a id="s2-1"></a>2.1 Strategic Environment

- **Organizational Overview:**

  - **Mission:** Foster interdisciplinary neuroscience research with state-of-the-art tools and infrastructure.

  - **Strategic Goals:** Enable modular workflows, support sensitive data projects, and enhance collaboration<ins>; advance computational modelling and neuro-AI; practise open science in line with the SFU Principles</ins>.

  - **Current Activities:** Limited modularity and integration capabilities, restricting collaboration.

- **Business Need:**

  - Address gaps in infrastructure to enable modular workflows and integration with external services.

- **Drivers for Change:**

  - Increased demand for handling large, heterogeneous and shared datasets.

  - Increased demand for handling sensitive datasets.

  - Rising need to support interdisciplinary collaboration.

  - Advancements in data analysis and visualization technologies.

  - <ins>Growth of modelling and neuro-AI, which require GPU compute on sensitive imaging data and produce models that can themselves carry sensitive information.</ins>

  - <ins>Funder and institutional expectations for open science, including the SFU Open Science and Open Scholarship Principles ([Simon Fraser University 2025](#ref-sfuos)) and the Tri-Agency Research Data Management Policy ([Canadian Institutes of Health Research, Natural Sciences and Engineering Research Council of Canada, and Social Sciences and Humanities Research Council of Canada 2021](#ref-triagency2021rdm)).</ins>

- **Business Outcomes:**

  - Streamlined research processes.

  - Improved collaboration and reduced redundancy.

  - Expanded computational and analytical capabilities.

  - <ins>More INN outputs shared openly, at the most open level each allows.</ins>

> *New since June 2025.*
>
> ### <a id="s2-2"></a>2.2 INN Mission and Values
>
> INN’s mission and values ([Institute for Neuroscience and Neurotechnology, n.d.c](#ref-innvalues)) drive this strategy, including its open-science commitments.
>
> #### Vision.
>
> “Society is taking an integrative approach to supporting brain resilience that is comprehensive, individualized, and accessible for all.”
>
> #### Mission.
>
> The third of INN’s four mission objectives is the direct mandate for this infrastructure: “Enhance neuroscience research at SFU by providing technical support, that complements and advances investigator’s teams, for data acquisition and analysis, informatics, and computational modelling.” The others shape it as well: educating the world on brain resilience (open outputs), inspiring interdisciplinary, fundamental and translational research for clinical and commercial uses (partnerships, licensing), and training the next generation of researchers (training and usable tools).
>
> #### Values and what they ask of the infrastructure.
>
> | **Value**                       | **What it asks of the infrastructure**                                                                                                                                                          | **Where**                    |
> |:--------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------|
> | **Value**                       | **What it asks of the infrastructure**                                                                                                                                                          | **Where**                    |
> | Complex Systems Thinking        | People and social structures form an extended network that continuously informs how INN works. The infrastructure should track that network as it changes, rather than freeze a snapshot of it. | Proposal A (§[7](#s7))       |
> | Integrity and Ethics            | Consent and agreements are enforced, not only documented; every access is accountable; restrictions are explained.                                                                              | §3.2; W4.7; use case 5.7     |
> | Respect for All Members         | Participants may decline without penalty; communities and partners hold real authority over their data.                                                                                         | W4.7; §[2.9](#s2-9) (P3, P4) |
> | Interdisciplinary Collaboration | Modular tools, shared standards and integration across disciplines and institutions.                                                                                                            | §3.1; §3.4                   |
> | Accessible and Open Research    | Outputs are open by default, at the most open level each allows, and findable even when closed.                                                                                                 | §3.5; W4.8; §[2.8](#s2-8)    |
> | Accompaniment                   | Partners are supported, not burdened: their data is governed in place, INN components are not imposed inside their networks, and benefits flow back to contributing communities.                | §3.2; §3.4; use case 5.8     |

### <a id="s2-3"></a>2.3 Strategic Fit

- Aligns with INN’s mission and SFU’s strategic priorities<ins>, including the interdisciplinarity, community engagement and knowledge mobilization that SFU’s Open Scholarship Framework supports ([Simon Fraser University, n.d.b](#ref-sfuosframework))</ins>.

- Supports compliance with federal data management, SFU’s Research Data Management Strategy<ins> ([Canadian Institutes of Health Research, Natural Sciences and Engineering Research Council of Canada, and Social Sciences and Humanities Research Council of Canada 2021](#ref-triagency2021rdm); [Simon Fraser University, n.d.a](#ref-sfurdm))</ins>, and ethical frameworks.

- <ins>Implements the SFU Open Science and Open Scholarship Principles for INN research, in partnership with the university-wide Open Scholarship initiative ([Simon Fraser University, n.d.b](#ref-sfuosframework)).</ins>

- <ins>Supports TCPS2 ([Canadian Institutes of Health Research, Natural Sciences and Engineering Research Council of Canada, and Social Sciences and Humanities Research Council of Canada 2022](#ref-tcps2)), the First Nations Principles of OCAP ([First Nations Information Governance Centre, n.d.](#ref-ocap)), the CARE Principles for Indigenous Data Governance ([Carroll et al. 2020](#ref-carroll2020care)), and applicable privacy law.</ins>

### <a id="s2-4"></a>2.4 Detailed Description of the Business Need

- **Problem Statement:** Existing infrastructure is insufficient for modular research workflows and integration.

- **Requirements:**

  - Core: Secure data management, modular workflows, and governance compliance<ins>; tiered access from open to restricted; agreement-aware sharing; FAIR metadata for outputs</ins>.

  - Desirable: Scalable storage and computational resources, and customizable visualization tools<ins>; GPU compute for modelling and neuro-AI on restricted data</ins>.

  - Optional: Training modules for researchers.

- **Assumptions:** Sufficient funding will be secured; existing infrastructure can be partially leveraged.

- **Constraints:** Limited budget and expertise in certain areas.

### <a id="s2-5"></a>2.5 Scope

- **Boundaries:**

  - Included: Research design consulting, data storage, computation, and visualization<ins>; sharing; dissemination and deposit of research outputs, including models</ins>.

  - Excluded: Long-term data archiving solutions. <ins>Persistence for published outputs is achieved by depositing in existing repositories (e.g., SFU Summit ([SFU Library, n.d.](#ref-summit)), Borealis ([Borealis, n.d.](#ref-borealis)), disciplinary repositories such as OpenNeuro ([Markiewicz et al. 2021](#ref-markiewicz2021openneuro))), not by building an archive.</ins>

- **Stakeholder Analysis:**

  - Internal: INN researchers, SFU ImageTech Lab, SFU administration<ins>, SFU Library, Office of Research Ethics, the university Open Scholarship initiative</ins>.

  - External: Health authorities, partnering academic institutions, industry partners, community research partners.

> *New since June 2025.*
>
> ### <a id="s2-6"></a>2.6 High-Friction Challenges in INN Research
>
> The infrastructure must be designed for the places where INN research gets stuck.
>
> | **Challenge**                            | **Where it arises**                                                                                                                                                                                                                                                                | **Infrastructure implication**                                                                                                                                                              |
> |:-----------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
> | **Challenge**                            | **Where it arises**                                                                                                                                                                                                                                                                | **Infrastructure implication**                                                                                                                                                              |
> | Consent scope and secondary use          | Clinical imaging, cohort studies, reuse of hospital data                                                                                                                                                                                                                           | Consent and agreement terms travel with the data; every reuse is checked against them.                                                                                                      |
> | Re-identification risk                   | MRI and other imaging (faces are reconstructable ([Schwarz et al. 2019](#ref-schwarz2019))), small cohorts, linked records                                                                                                                                                         | Tiered access, de-identification (e.g., defacing ([Bischoff-Grethe et al. 2007](#ref-bischoffgrethe2007))), controlled environments, release review before outputs leave a restricted tier. |
> | Cross-institution agreements             | Surrey Memorial Hospital and other health-authority partners, multi-site studies                                                                                                                                                                                                   | Data usage agreements gate sharing; partner data is governed in place without transferring ownership.                                                                                       |
> | Large transfers out of hospital networks | Imaging studies of 100 GB or more, restrictive clinical networks                                                                                                                                                                                                                   | Resumable, unattended, outbound-only transfer over standard ports, with no component the hospital must host.                                                                                |
> | Model leakage                            | Neuro-AI models trained on patient data, which can leak training data through membership inference or memorization ([Shokri et al. 2017](#ref-shokri2017); [Carlini et al. 2023](#ref-carlini2023))                                                                                | Models are treated as potentially sensitive outputs: release review, provenance, and differential privacy ([Dwork and Roth 2014](#ref-dwork2014)) where required.                           |
> | GPU compute on restricted data           | Modelling and neuro-AI training                                                                                                                                                                                                                                                    | Restricted data can reach GPUs only in environments appropriate to its tier.                                                                                                                |
> | Heterogeneous formats and metadata       | DICOM ([National Electrical Manufacturers Association, n.d.](#ref-dicom)), NIfTI ([Data Format Working Group, n.d.](#ref-nifti)), BIDS ([Gorgolewski et al. 2016](#ref-gorgolewski2016bids)), NWB ([Rübel et al. 2022](#ref-rubel2022nwb)), electrophysiology and behavioural data | Validation against community standards (e.g., the BIDS validator) at ingest.                                                                                                                |
> | Reproducibility and provenance           | Pipelines, models and derived datasets                                                                                                                                                                                                                                             | Versioned data and containers; recorded configurations and inputs for every result and model.                                                                                               |
> | Indigenous data sovereignty              | Community-partnered research                                                                                                                                                                                                                                                       | OCAP- and CARE-aligned governance ([First Nations Information Governance Centre, n.d.](#ref-ocap); [Carroll et al. 2020](#ref-carroll2020care)); data can remain under community control.   |
> | Modality-specific risk                   | Structural MRI can identify a person; functional MRI and EEG can encode mental states                                                                                                                                                                                              | Risk tiers set by modality, not a single “neural data” category ([Ray et al. 2026](#ref-ray2026)).                                                                                          |
> | Jurisdiction and data sovereignty        | International collaborators; data localization and cross-border transfer rules                                                                                                                                                                                                     | Jurisdictional constraints recorded with the data; analysis brought to data that cannot move ([Ray et al. 2026](#ref-ray2026)).                                                             |
>
> ### <a id="s2-7"></a>2.7 Design Stance: Not Repeating Inherited Errors
>
> For several of the problems this strategy addresses, an easier solution exists and has been widely adopted. Its costs are now documented. INN deliberately takes the harder path where the easier one would repeat these errors. The examples below draw on a recent analysis of neuroscience data governance ([Ray et al. 2026](#ref-ray2026)).
>
> | **Easier solution**                                      | **Documented cost**                                                                                                                                                                               | **INN’s approach**                                                                                   |
> |:---------------------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------|
> | **Easier solution**                                      | **Documented cost**                                                                                                                                                                               | **INN’s approach**                                                                                   |
> | Lock data inside one commercial analysis platform        | When UK Biobank moved to a mandatory cloud platform, imaging researchers estimated analysis costs up to ten times higher than on institutional computing, pricing out under-resourced researchers | Federated compute on shared national infrastructure; data governed in place                          |
> | Treat all neural data as one category                    | Safeguards end up either too weak for high-risk modalities or too restrictive for low-risk ones                                                                                                   | Modality-specific risk tiers                                                                         |
> | Govern raw data only                                     | Value and risk increasingly sit in models trained on the data, which escape data-centric controls                                                                                                 | Models governed as outputs: release review, provenance, registry (use case 5.6)                      |
> | Governance as documents and case-by-case negotiation     | Fragmented, opaque access pathways; institutions over-restrict when uncertain, even where sharing is permitted                                                                                    | Machine-readable governance attached to data, enforced automatically (§3.2)                          |
> | Consent captured once, at collection                     | Scope changes and withdrawals do not reach reused and derived data                                                                                                                                | Dynamic consent ([Kaye et al. 2015](#ref-kaye2015)), with withdrawal propagated (W4.7; use case 5.7) |
> | Collect data from partners with little local involvement | “Parachute science” and data colonialism erode trust and participation                                                                                                                            | Accompaniment: partner control, benefit return, community governance                                 |
> | Assess risk once                                         | Re-identification and inference capabilities advance; yesterday’s safe release becomes unsafe                                                                                                     | Periodic risk reassessment (§3.2)                                                                    |
>
> ### <a id="s2-8"></a>2.8 Implementation Principle: Open and Reusable by Design
>
> **Infrastructure built for INN is built to be open and reusable.** This principle governs *how* INN’s infrastructure is built, not whom it serves. The work remains scoped to INN’s research needs. Openness means that what INN builds can also be adopted by others, including the SFU Open Scholarship community and INN’s external partners, at no additional cost to INN.
>
> #### Grounding.
>
> The principle follows from INN’s value of Accessible and Open Research ([Institute for Neuroscience and Neurotechnology, n.d.c](#ref-innvalues)), from the Open Scholarship Principles’ preference for open-source tools and interoperable, FAIR outputs ([Simon Fraser University 2025](#ref-sfuos); [Wilkinson et al. 2016](#ref-wilkinson2016fair)) and their encouragement of open licences ([Simon Fraser University 2025](#ref-sfuos)), and from INN’s design stance (Section [2.7](#s2-7)). Proprietary or bespoke infrastructure recreates the lock-in and fragmentation documented in neuroscience data governance ([Ray et al. 2026](#ref-ray2026)).
>
> #### Commitments.
>
> 1.  **Open source by default.** Software is released under an open-source licence unless a specific restriction applies (for example, security-sensitive configuration or a partner agreement), in which case the reason is recorded.
>
> 2.  **Adopt, then connect, then build.** Existing open standards and tools are adopted where they fit (e.g., BIDS ([Gorgolewski et al. 2016](#ref-gorgolewski2016bids)), NWB ([Rübel et al. 2022](#ref-rubel2022nwb))<ins>; workflow, tracking and transfer tools such as Galaxy, MLflow, DataLad and Globus</ins>); where standards exist but do not connect, INN writes the connecting layer; new designs are created only for the gaps that remain.
>
> 3.  **Interfaces as contracts.** Components interact through documented, versioned, public interfaces (APIs, data formats, protocols), so that each can be reused or replaced independently of INN-specific internals.
>
> 4.  **Mechanism separate from policy.** INN’s governance rules (agreements, risk tiers, consent terms) are expressed as configuration in documented formats rather than hard-coded, so that others can reuse the mechanism with their own rules.
>
> 5.  **Documented for reuse.** Components ship with documentation, examples and a reference deployment.
>
> 6.  **Open code, protected data.** Openness applies to software, interfaces and documentation, never to restricted data, credentials or security-sensitive configuration. Security issues are handled through responsible disclosure.
>
> #### Why it serves INN.
>
> Open infrastructure avoids vendor lock-in, invites external review (including security review), lets INN align with community efforts such as BRIDGE ([Ray et al. 2026](#ref-ray2026)) instead of diverging from them, and allows maintenance to be shared with other adopters over time.
>
> ### <a id="s2-9"></a>2.9 Alignment with the Open Scholarship Principles
>
> The SFU Open Science and Open Scholarship Principles ([Simon Fraser University 2025](#ref-sfuos)) are the institutional framework through which INN practises its value of Accessible and Open Research. They shape how INN implements this strategy:
>
> 1.  **Equitable practice.** Infrastructure is usable by hospital, community and external partners, not only SFU researchers.
>
> 2.  **Open sharing.** Outputs are FAIR ([Wilkinson et al. 2016](#ref-wilkinson2016fair)), open-source tools are preferred, and where data cannot be shared, the reason is stated.
>
> 3.  **Participant autonomy.** Participants may decline open-science activities without penalty.
>
> 4.  **Dignity and privacy.** Consent, withdrawal, data usage agreements and collective ownership are enforced, not only documented.
>
> 5.  **Institutional support.** A sustainable model for infrastructure, training (e.g., the Open Scholarship starter kit ([Open Scholarship at SFU 2026](#ref-sfustarterkit2026))) and recognition.
>
> 6.  **Harmonized IP.** Open licences are encouraged, and licence terms may prohibit misuse.
>
> Openness is the default for INN outputs, never a precondition for using the infrastructure. Section [6](#s6) traces each goal and workflow to these principles.

## <a id="s3"></a>3 Goals

### <a id="s3-1"></a>3.1 Modular Digital Infrastructure for Neuroscience Research

- **Objective**:

  - Develop a flexible and scalable digital platform to support modular workflows in neuroscience research, from pre-planning to visualization.

- **Strategic Context**:

  - **Business Need**: Current systems do not allow seamless transitions between research phases or easy integration of external services.

  - **Drivers for Change**: Increased demand for flexible, modular workflows to handle large, sensitive datasets.

  - **Business Outcomes**:

    - Streamlined research processes.

    - Reduced redundancy in data handling.

    - Increased research efficiency and output.

- **Analysis and Recommendation**:

  - **Options**:

    - Enhance current systems (partial modularity).

    - Build a comprehensive modular platform (full cycle support).

    - <ins>Adopt a commercial data science and machine learning (DSML) platform (e.g., IBM Watson Studio, Databricks).</ins>

    - <ins>Assemble a modular platform from open components (e.g., Galaxy, Open OnDemand, MLflow, DataLad), building only what they lack.</ins>

  - **Preferred Option**: Develop a comprehensive modular platform due to its scalability and alignment with strategic goals<ins>, assembled from open components where they fit (Section [2.8](#s2-8)). In industry terms this is a DSML platform; in research computing terms, a science gateway, run on SFU and Alliance infrastructure. The direction is to build only what open components lack, chiefly the governance layer, of which the INN Data Portal is the first piece; specific components are chosen year by year in INN’s operating plan</ins>.

  - **Risks**: High initial cost; mitigated through phased development <ins>and reuse of open components. A commercial DSML platform would reduce build effort but recreate the lock-in described in Section [2.7](#s2-7)</ins>.

- **Management and Capacity**:

  - Establish a governance team to oversee modularity standards.

  - Engage stakeholders early to ensure alignment with research needs.

### <a id="s3-2"></a>3.2 Secure Data Management for Sensitive and Heterogeneous Datasets

- **Objective**: Implement a secure and compliant data management framework for handling diverse and sensitive datasets in neuroscience research<ins>, making data as open as possible and as closed as necessary</ins>.

- **Strategic Context**:

  - **Business Need**: Current data systems are inadequate for large, multi-institutional datasets requiring high security and compliance.

  - **Drivers for Change**: Increasing complexity and sensitivity of datasets; evolving regulatory requirements.

  - **Business Outcomes**:

    - Enhanced data integrity and compliance.

    - Improved collaboration through secure sharing mechanisms.

    - <ins>Metadata for restricted data remains findable, with the restriction and its reason stated.</ins>

- **Analysis and Recommendation**:

  - **Options**:

    - Expand current data storage systems.

    - Implement a new, compliant data management framework.

  - **Preferred Option**: Implement a new framework to meet future demands. <ins>The framework separates who governs access from where data is stored, so partner data (e.g., hospital imaging) can remain in the partner’s storage while access is managed consistently. The INN Data Portal already implements this separation. Governance attributes (modality, risk tier, consent scope, jurisdictional constraints, permitted processing contexts) are recorded as machine-readable metadata with the data and its derivatives. They route each request to the appropriate access pathway: open, registered, controlled environment, or analysis in place ([Ray et al. 2026](#ref-ray2026)).</ins>

  - **Risks**: High resource demands; mitigated by leveraging existing infrastructure.

- **Management and Capacity**:

  - Conduct regular security audits.

  - <ins>Reassess re-identification, inference and model-leakage risk periodically, as analytical capabilities advance ([Ray et al. 2026](#ref-ray2026)).</ins>

  - Collaborate with external partners for compliance standards.

### <a id="s3-3"></a>3.3 Advanced Computational Tools for Neuroscience

- **Objective**:

  - Provide high-performance computational resources for advanced analysis, modelling, and visualization in neuroscience research<ins>, including neuro-AI model training on sensitive data</ins>.

- **Strategic Context**:

  - **Business Need**: Researchers lack access to scalable computation for analyzing large, complex datasets.

  - **Drivers for Change**: Growing need for brain simulations and data-intensive analysis<ins>; GPU-intensive neuro-AI training on restricted imaging data</ins>.

  - **Business Outcomes**:

    - Increased computational efficiency.

    - New research capabilities in modelling and visualization.

- **Analysis and Recommendation**:

  - <ins>**Current State**: INN operates in a federated environment, using the Digital Research Alliance of Canada ([Digital Research Alliance of Canada, n.d.](#ref-alliance)) and SFU research computing for most work, with private compute reserved for highly sensitive data.</ins>

  - **Options**:

    - Outsource computation to external HPC providers.

    - Develop an in-house HPC platform integrated with the ecosystem.

    - <ins>Continue the federated model and strengthen its integration with the ecosystem, keeping private compute for the highest sensitivity tier.</ins>

  - **Preferred Option**: <ins>Continue and integrate the federated model, with private compute for the highest tier. (The June 2025 strategy preferred an in-house HPC platform; this revision reflects current practice.)</ins> <mark>Proposal B (Section [7](#s7)) sets out how confidential computing could reduce dependence on private compute.</mark>

  - **Risks**: High cost and technical expertise requirements; mitigated through phased scaling.

- **Management and Capacity**:

  - Partner with SFU’s research computing resources.

  - Implement user-friendly interfaces for accessibility.

### <a id="s3-4"></a>3.4 External Service Integration for Collaborative Research

- **Objective**: Enable seamless integration of external services (e.g., hospital data systems, other academic platforms) with the research ecosystem.

- **Strategic Context**:

  - **Business Need**: Lack of interoperability between INN services and external systems hampers collaboration.

  - **Drivers for Change**: Increasing demand for cross-institutional research collaboration.

  - **Business Outcomes**:

    - Enhanced interoperability and collaboration.

    - Improved research continuity and data utilization.

- **Analysis and Recommendation**:

  - **Options**:

    - Maintain siloed systems with limited integration.

    - Build APIs and frameworks for external service integration.

  - **Preferred Option**: Develop APIs and frameworks for dynamic service integration<ins>, based on open standards where available</ins>.

  - **Risks**: Complexity of managing diverse standards; mitigated through pilot programs. <ins>Integration that requires partners to host and administer INN components inside their networks is a significant adoption barrier and should be avoided where possible.</ins>

- **Management and Capacity**:

  - Establish a task force to define integration standards.

  - Test interoperability with pilot projects before full-scale rollout.

> *New since June 2025.*
>
> ### <a id="s3-5"></a>3.5 Open Dissemination of Research Outputs
>
> - **Objective**: Make it straightforward to publish, license and receive credit for INN research outputs: data, code, pipelines, models and preprints.
>
> - **Strategic Context**:
>
>   - **Business Need**: Outputs other than articles are rarely deposited, identified or cited. Models trained on sensitive data have no defined release path.
>
>   - **Drivers for Change**: Principle 2 (FAIR sharing of what is needed to reproduce research); Principle 5 (recognition); the growth of neuro-AI models as research outputs.
>
>   - **Business Outcomes**:
>
>     - More INN outputs with persistent identifiers.
>
>     - A safe, reviewable release path for models trained on restricted data.
>
> - **Analysis and Recommendation**:
>
>   - **Options**: Leave deposit to individual researchers; or integrate deposit, licensing, release review and identifier minting into workflows.
>
>   - **Preferred Option**: Integrate deposit into workflows.
>
>   - **Risks**: Premature release of sensitive outputs; mitigated by release review and metadata validation.
>
> - **Management and Capacity**:
>
>   - Partner with SFU Library on repositories, identifiers and licensing.

### <a id="s3-6"></a>3.6 Long-Term Sustainability and Evolution

- **Objective**: Secure funding and create a governance model to ensure the ecosystem’s long-term sustainability.

- **Strategic Context**:

  - **Business Need**: The ecosystem requires consistent updates and support to stay relevant and functional.

  - **Drivers for Change**: Rapid advancements in neuroscience tools and methods.

  - **Business Outcomes**:

    - Stable and evolving research support infrastructure.

    - Increased user trust and system adoption.

- **Analysis and Recommendation**:

  - **Options**:

    - Rely on grant-based funding with ad hoc updates.

    - Establish a funded governance body with a sustainability plan.

  - **Preferred Option**: Establish a funded governance body to ensure reliability.

  - **Risks**: Dependency on external funding; mitigated through diversification of funding sources.

- **Management and Capacity**:

  - Implement performance monitoring metrics.

  - Establish partnerships for shared funding responsibilities.

## <a id="s4"></a>4 Workflows

### <a id="s4-1"></a>4.1 Secure Data Storage and Access

- **Workflow Overview:**

  - Researchers securely store complex datasets, some of which are sensitive and contain personal identifiable information (PII), ensuring compliance with legal and ethical standards.

- **Steps:**

  1.  Registered users log into the platform via a browser.

  2.  Users can see specific data assets they have been granted access to, which they can upload or download.

  3.  The user selects the resource they would like to upload to/download from.

  4.  Data is uploaded/downloaded via a secure interface, where the system ensures proper format and metadata alignment<ins>, validated against neuroscience standards such as BIDS</ins>.

  5.  Data is securely stored with appropriate access controls.

  6.  Notifications confirm successful uploads and compliance adherence.

- **Outcome:**

  - Researchers trust that, if necessary, sensitive data is protected and accessible only to authorized personnel, with transparent logging for accountability.

  - Researchers have access to a variety of storage environments, e.g., PII secure/insecure, as needed.

  - The system is able to scale with a large number and size of files.

  - The system is able to handle frequent and infrequent data transfers, e.g., regular uploads from field study recorded data or one-time uploads for large data sets.

  - Uploaded data may be integrated seamlessly into other workflows (e.g., 4.3).

### <a id="s4-2"></a>4.2 Data Sharing

- **Workflow Overview:**

  - Researchers can share access to stored datasets, some of which are sensitive and contain PII, ensuring compliance with legal and ethical standards.

- **Steps:**

  1.  Registered users log into the platform via a browser.

  2.  Users can see specific data assets they have been granted different levels of access to (e.g., read, write) which they can share.

  3.  The user may select the resources they would like to share with a collaborator (which may or may not be a registered user).

  4.  If the data asset is bound by access agreements, the generation of a method of access to share with a collaborator is dependent on fulfillment and record of the agreement (e.g., the collaborator may need to sign an access agreement).

  5.  The user generates the method of access that can be shared with the collaborator.

  6.  The collaborator can access the data asset for viewing, uploading, or downloading via the method of access.

- **Outcome:**

  - Registered users can easily manage sharing to fulfill research collaboration, with the ability to specify access constraints depending on the specifications of access agreements associated with the data asset.

  - Specifications of data access agreements for assets the user has access to are propagated to sharing interactions extended from the user to collaborators.

### <a id="s4-3"></a>4.3 Data Preparation and Computational Analysis

- **Workflow Overview:** Researchers run advanced computational workflows on securely stored datasets to derive insights and results.

- **Steps:**

  1.  Researchers select predefined computational workflows from a catalog.

  2.  The system retrieves relevant data and allocates computational resources<ins>, keeping restricted data within an environment appropriate to its tier</ins>.

  3.  Data preparation and analysis is conducted, and results are securely stored in a temporary location<ins>, together with a provenance record</ins>.

  4.  Researchers are notified of completion and can securely access results.

- **Outcome:**

  - Complex workflows and analyses are completed efficiently, empowering researchers to focus on interpretation and decision-making.

### <a id="s4-4"></a>4.4 Custom Computational Pipeline Development

- **Workflow Overview:**

  - Researchers design and execute tailored analysis pipelines to address unique research questions.

- **Steps:**

  1.  Researchers access a modular interface to select analytical tools and data processing steps.

  2.  Pipelines are configured and validated for compatibility and resource needs.

  3.  The system executes the custom pipeline, storing the results securely.

  4.  Configurations and outputs are logged for reproducibility.

- **Outcome:**

  - Modular tools empower innovation and customized research workflows.

### <a id="s4-5"></a>4.5 Retrieving Analytical Results

- **Workflow Overview:**

  - Researchers retrieve results of completed computational workflows for further study or sharing.

- **Steps:**

  1.  Researchers log into their accounts and access a list of completed analyses.

  2.  <ins>Results derived from restricted data pass a release check before leaving the restricted tier.</ins>

  3.  The system provides secure, on-demand access to the results.

  4.  Results are downloaded or shared securely for collaboration.

- **Outcome:**

  - Simplified access to critical data reduces administrative overhead and facilitates quick decision-making.

### <a id="s4-6"></a>4.6 External Data Integration for Analysis

- **Workflow Overview:**

  - Researchers incorporate datasets from external sources for analysis within the ecosystem.

- **Steps:**

  1.  Researchers provide credentials and secure access details for external datasets.

  2.  The system retrieves and validates the external data<ins>, or runs the analysis where the data resides if the holder requires it (e.g., federated learning with a hospital partner ([Rieke et al. 2020](#ref-rieke2020)))</ins>.

  3.  Computational workflows are executed as requested.

  4.  Results are securely returned without permanently storing external data.

- **Outcome:**

  - Seamless integration with external data sources expands research capabilities without compromising security.

> *New since June 2025.*
>
> ### <a id="s4-7"></a>4.7 Consent, Withdrawal and Community Governance
>
> - **Workflow Overview:** Participant consent and community governance decisions are recorded with the data they govern and enforced throughout its life, including participants’ right to decline or withdraw (Principles 3–4).
>
> - **Steps:**
>
>   1.  At collection, consent terms (permitted uses, sharing tiers, duration, withdrawal mechanism) are attached to the data as machine-readable metadata.
>
>   2.  Where data is collectively owned or subject to OCAP, designated community stewards hold governance roles over access decisions.
>
>   3.  Every access, share or reuse request is checked against the consent terms and governance decisions in force.
>
>   4.  On withdrawal, the change is applied to the source data and flagged on known shared copies and derived datasets, as far as technically possible.
>
> - **Outcome:** Consent and governance are enforced rather than merely documented.
>
> ### <a id="s4-8"></a>4.8 Publishing and Depositing Research Outputs
>
> - **Workflow Overview:** Researchers publish data, code, pipelines and models as FAIR, licensed and citable objects, at the most open tier each allows.
>
> - **Steps:**
>
>   1.  The researcher selects outputs and the most open tier permitted (open, controlled access, or metadata only).
>
>   2.  The system checks metadata completeness and consent and agreement compatibility. It offers de-identification (e.g., defacing of MRI ([Bischoff-Grethe et al. 2007](#ref-bischoffgrethe2007))) where it applies. Models trained on restricted data pass release review.
>
>   3.  The researcher chooses a licence, optionally with terms prohibiting identified misuses.
>
>   4.  The output is deposited in an appropriate repository (e.g., SFU Summit for articles ([SFU Library, n.d.](#ref-summit)); OpenNeuro ([Markiewicz et al. 2021](#ref-markiewicz2021openneuro)), Borealis ([Borealis, n.d.](#ref-borealis)) or DANDI ([DANDI Archive, n.d.](#ref-dandi)) for data), and a persistent identifier is minted.
>
>   5.  For restricted outputs, a public metadata record states the restriction, the reason, and how to request access.
>
> - **Outcome:** Outputs are findable and citable even when the data itself is closed.

## <a id="s5"></a>5 Use Cases and System Requirements

### <a id="s5-1"></a>5.1 Storing Personal Identifiable Information (PII)

**Relevant Business Cases:**

- **Business Case 2: Secure Data Management for Sensitive and Heterogeneous Datasets**.

- **Business Case 4: External Service Integration for Collaborative Research**.

**Actors:**

- **Researcher**: Uploads PII data for storage.

- **INN Digital Ecosystem**: Provides secure, compliant storage.

- **Data Governance Administrator**: Ensures data meets compliance standards.

**Preconditions:**

1.  Researcher has an active account with appropriate permissions.

2.  Data collection complies with ethical and legal standards.

3.  Storage space is allocated for the researcher’s project.

4.  <ins>Consent terms and governing agreements are available to attach.</ins>

**Trigger:**

Researcher initiates the upload of PII data via the platform.

**Main Flow:**

1.  Researcher logs into the platform.

2.  Data is uploaded through a secure, encrypted channel.

3.  The platform validates the data format and metadata for completeness<ins>, including consent and agreement metadata</ins><mark>; data declared as BIDS is validated against the BIDS specification ([Gorgolewski et al. 2016](#ref-gorgolewski2016bids))</mark>.

4.  Data is stored securely, with encryption at rest and access control.

5.  Notifications are sent to the researcher confirming successful storage.

**Postconditions:**

- Data is securely stored and accessible only to authorized users.

- An audit log of the upload process is recorded.

**Exceptions:**

- **Format Validation Failure**: Notify researcher to correct and re-upload.

- **Insufficient Storage**: Notify researcher to request additional allocation.

- <ins>**Missing Consent or Agreement Metadata**: Hold data in quarantine and notify researcher.</ins>

- <mark>**BIDS Validation Failure**: Hold data declared as BIDS in quarantine and report what failed.</mark>

**Functional Requirements:**

- Secure data upload channels.

- Validation of data format and metadata<mark>, including BIDS where declared</mark>.

- Encryption and access control mechanisms.

**Non-Functional Requirements:**

- Compliance with relevant regulations (e.g., GDPR<ins> ([European Parliament and Council of the European Union 2016](#ref-gdpr))</ins>, HIPAA<ins> ([United States Congress 1996](#ref-hipaa)), BC FIPPA ([Province of British Columbia, n.d.](#ref-fippa)); TCPS2 ([Canadian Institutes of Health Research, Natural Sciences and Engineering Research Council of Canada, and Social Sciences and Humanities Research Council of Canada 2022](#ref-tcps2)); OCAP/CARE where applicable ([First Nations Information Governance Centre, n.d.](#ref-ocap); [Carroll et al. 2020](#ref-carroll2020care))</ins>).

- High availability of storage systems.

- Logging and audit capabilities.

### <a id="s5-2"></a>5.2 Computational Pipeline on PII Data

**Relevant Business Cases:**

- **Business Case 3: Advanced Computational Tools for Neuroscience**.

- **Business Case 2: Secure Data Management for Sensitive and Heterogeneous Datasets**.

**Actors:**

- **Researcher**: Requests computational analysis on PII data.

- **INN Digital Ecosystem**: Provides computational pipelines.

- **Compute Resource Manager**: Allocates appropriate resources for computation.

**Preconditions:**

1.  PII data is already stored on the platform.

2.  Researcher has permissions to run computational pipelines.

3.  Computational workflows have been pre-validated for compliance.

**Trigger:**

Researcher selects a computational pipeline to analyze the stored PII data.

**Main Flow:**

1.  Researcher logs in and selects the desired computational workflow.

2.  The platform retrieves the stored PII data securely.

3.  Compute resources are allocated, and the pipeline is executed<ins>, in private compute where the data’s tier requires it</ins>.

4.  Results are encrypted and stored in a temporary output location.

**Postconditions:**

- Computation is completed, and results are securely stored.

- Notifications are sent to the researcher upon completion.

**Exceptions:**

- **Pipeline Errors**: Notify researcher with debugging details.

- **Insufficient Compute Resources**: Notify researcher to reschedule the analysis.

**Functional Requirements:**

- Secure retrieval of PII data for analysis.

- Scalable compute resource allocation.

- Logging of computational processes.

- <mark>Pipelines on BIDS inputs run as BIDS Apps, and write BIDS derivatives that name the software and source datasets that produced them.</mark>

**Non-Functional Requirements:**

- High performance and reliability for large-scale computation.

- End-to-end data security during computation.

- Compliance with data privacy standards.

### <a id="s5-3"></a>5.3 Retrieving Computational Pipeline Results

**Relevant Business Cases:**

- **Business Case 3: Advanced Computational Tools for Neuroscience**.

- **Business Case 4: External Service Integration for Collaborative Research**.

**Actors:**

- **Researcher**: Retrieves results from a completed computational pipeline.

- **INN Digital Ecosystem**: Provides secure access to results.

**Preconditions:**

1.  Researcher has completed a computational workflow on the platform.

2.  Results are securely stored and ready for retrieval.

**Trigger:**

Researcher initiates a request to retrieve pipeline results.

**Main Flow:**

1.  Researcher logs into the platform and navigates to the completed workflow.

2.  <ins>If results derive from restricted data, a release check is applied.</ins>

3.  Results are retrieved securely, with encryption during transit.

4.  Researcher downloads the results to their local environment.

**Postconditions:**

- Results are successfully retrieved.

- Access logs are updated to reflect the retrieval.

**Exceptions:**

- **Access Denied**: Notify researcher to resolve permission issues.

- **Result Corruption**: Notify researcher and request re-computation.

**Functional Requirements:**

- Secure result retrieval mechanisms.

- User-friendly interface for browsing completed workflows.

- Notifications for retrieval status.

- <mark>Results from BIDS inputs are retrieved as BIDS derivatives, with their provenance.</mark>

**Non-Functional Requirements:**

- Data integrity assurance during retrieval.

- Detailed audit logs of result access.

- Minimal latency for result download.

### <a id="s5-4"></a>5.4 External PII Data for Computational Pipeline

**Relevant Business Cases:**

- **Business Case 3: Advanced Computational Tools for Neuroscience**.

- **Business Case 4: External Service Integration for Collaborative Research**.

**Actors:**

- **Researcher**: Provides external PII data and requests computational analysis.

- **INN Digital Ecosystem**: Executes the computational pipeline and returns results.

**Preconditions:**

1.  Researcher has an active account and proper permissions on the platform.

2.  PII data resides in the researcher’s external storage system and meets format and compliance requirements.

3.  Researcher grants the platform secure, temporary access to the data.

**Trigger:**

Researcher initiates the request to process externally stored PII data through the platform.

**Main Flow:**

1.  Researcher logs into the platform and specifies the location and credentials for accessing external PII data.

2.  Platform establishes a secure, encrypted connection to the external storage domain and retrieves the specified dataset.

3.  Platform validates the data format and compliance.

4.  Computational pipeline is executed using the retrieved data.

5.  Results are encrypted and securely delivered to the researcher.

**Postconditions:**

- External PII data is processed securely without being permanently stored on the platform.

- Results are successfully delivered to the researcher.

- An audit log is maintained for compliance and accountability.

**Exceptions:**

- **Connection Failure**: Notify researcher to verify external storage credentials or network status.

- **Data Validation Failure**: Notify researcher to correct data format or compliance issues.

- **Pipeline Errors**: Notify researcher with debugging information and options to retry.

**Functional Requirements:**

- Secure, encrypted connection to external storage systems.

- Real-time validation of external data format and compliance.

- Execution of computational pipelines with secure handling of data.

**Non-Functional Requirements:**

- High reliability and security for data transfer.

- Scalability to handle large external datasets.

- Detailed logging for traceability and compliance.

### <a id="s5-5"></a>5.5 Building Custom Computational Pipelines

**Relevant Business Cases:**

- **Business Case 3: Advanced Computational Tools for Neuroscience**.

- **Business Case 1: Modular Digital Infrastructure for Neuroscience Research**.

**Actors:**

- **Researcher**: Designs and builds a custom computational pipeline.

- **INN Digital Ecosystem**: Provides modular pipeline components and computational resources.

**Preconditions:**

1.  Researcher has an active account with access to modular pipeline services.

2.  Required pipeline modules and computational resources are available within the platform.

3.  Researcher has permissions to create and run custom workflows.

**Trigger:**

Researcher initiates the process to create a custom computational pipeline using available modular services.

**Main Flow:**

1.  Researcher logs into the platform and navigates to the pipeline creation interface.

2.  Researcher selects desired modules from the library of available services (e.g., data preprocessing, analysis, visualization).

3.  Researcher configures the sequence and parameters for each module in the pipeline.

4.  Platform validates the pipeline configuration for compatibility and resource availability.

5.  The pipeline is executed on the platform’s computational resources.

6.  Results are stored securely and made accessible to the researcher.

**Postconditions:**

- Custom pipeline is successfully executed, and results are securely stored.

- The platform records the pipeline configuration and execution details for future reference.

**Exceptions:**

- **Module Compatibility Issues**: Notify researcher to adjust module selection or configuration.

- **Insufficient Resources**: Notify researcher to reschedule execution or modify pipeline scope.

- **Pipeline Errors**: Notify researcher with debugging information and suggestions for resolution.

**Functional Requirements:**

- Intuitive interface for selecting and configuring pipeline modules.

- Validation of module compatibility and resource requirements.

- Secure execution of custom pipelines.

**Non-Functional Requirements:**

- High scalability to support complex and resource-intensive pipelines.

- Robust error handling and debugging support.

- Logging and audit trails for pipeline configuration and execution.

> *New since June 2025.*
>
> ### <a id="s5-6"></a>5.6 Training a Neuro-AI Model on Restricted Imaging Data
>
> **Relevant Business Cases:**
>
> - **Business Case 3: Advanced Computational Tools for Neuroscience**.
>
> - **Business Case 2: Secure Data Management for Sensitive and Heterogeneous Datasets**.
>
> - **Business Case 5: Open Dissemination of Research Outputs**.
>
> **Actors:**
>
> - **Researcher**: Trains a model on restricted imaging data.
>
> - **INN Digital Ecosystem**: Provides the controlled training environment and release path.
>
> - **Compute Resource Manager**: Allocates GPU resources appropriate to the data’s tier.
>
> - **Data Steward**: Represents the data holder where the agreement requires it.
>
> **Preconditions:**
>
> 1.  The imaging data is stored on, or accessible through, the platform.
>
> 2.  The data’s consent and agreement terms permit model training for the stated purpose.
>
> 3.  A training environment appropriate to the data’s tier is available.
>
> **Trigger:**
>
> Researcher submits a training job.
>
> **Main Flow:**
>
> 1.  Researcher selects the dataset and a versioned, containerized training pipeline.
>
> 2.  The platform checks that the agreement permits training for the stated purpose.
>
> 3.  Data is provided to a GPU environment appropriate to its tier (private compute for the highest tier). Raw data does not leave that environment.
>
> 4.  Training runs. Checkpoints and intermediate outputs stay inside the environment.
>
> 5.  The trained model and its metrics undergo release review before leaving: an assessment of memorization and membership-inference risk ([Shokri et al. 2017](#ref-shokri2017); [Carlini et al. 2023](#ref-carlini2023)), with differential privacy ([Dwork and Roth 2014](#ref-dwork2014)) where the data’s terms require it.
>
> 6.  The released model is deposited with provenance (data version, code, parameters) and a licence that can restrict identified misuses. It is recorded in a model registry with its training-data lineage, intended use, jurisdictional scope and risk evaluation ([Ray et al. 2026](#ref-ray2026)).
>
> **Postconditions:**
>
> - The model is released, or retained inside the restricted tier.
>
> - Provenance and an audit record of the training run are kept.
>
> **Exceptions:**
>
> - **Purpose Not Permitted**: Notify researcher of the conflicting agreement term.
>
> - **Release Review Fails**: Retain the model internally, or retrain with stronger privacy protection.
>
> - **Insufficient GPU Resources**: Notify researcher to reschedule.
>
> **Functional Requirements:**
>
> - GPU allocation within environments matched to data tiers.
>
> - Release review for models trained on restricted data.
>
> - Provenance recording for training runs<mark>, including the BIDS selection a model was trained and validated on</mark>.
>
> **Non-Functional Requirements:**
>
> - No egress of raw restricted data from the training environment.
>
> - Reproducibility of training runs.
>
> - Audit of every training job and release decision.
>
> ### <a id="s5-7"></a>5.7 Withdrawing Participant Data
>
> **Relevant Business Cases:**
>
> - **Business Case 2: Secure Data Management for Sensitive and Heterogeneous Datasets**.
>
> **Actors:**
>
> Participant (or representative); Researcher; INN Digital Ecosystem; Data Governance Administrator.
>
> **Main Flow:**
>
> 1.  The withdrawal is recorded on the platform.
>
> 2.  The participant’s data is restricted or removed in the source dataset, as the consent terms specify.
>
> 3.  Shared copies, derived datasets and trained models that include the data are identified using provenance records<mark>; in BIDS data, the participant’s files are found by subject</mark>.
>
> 4.  Holders are notified, and new access to affected data is blocked.
>
> 5.  The participant receives confirmation of the actions taken.
>
> **Postconditions:**
>
> The withdrawal is enforced for all future access. Outputs that cannot be recalled (e.g., published aggregates, released models) are documented, consistent with what the participant was told at consent.
>
> ### <a id="s5-8"></a>5.8 Transferring Large Imaging Datasets out of a Hospital Network
>
> **Relevant Business Cases:**
>
> - **Business Case 4: External Service Integration for Collaborative Research**.
>
> **Actors:**
>
> Researcher; Hospital (data holder); INN Digital Ecosystem.
>
> **Main Flow:**
>
> 1.  The platform authorizes the request and issues time-limited access for each object.
>
> 2.  A transfer client at the destination fetches objects directly from storage over HTTPS (port 443). Bulk data does not pass through application servers.
>
> 3.  Interrupted transfers resume rather than restart, and run unattended, independent of a browser session.
>
> 4.  Integrity is verified on arrival, and the transfer is logged.
>
> **Non-Functional Requirements:**
>
> No platform component the hospital must host inside its network; minimal firewall changes; throughput for studies of 100 GB or more.

> **Proposal, not yet agreed.**
>
> ### <a id="s5-9"></a>5.9 Preparing a Dataset for Release
>
> **Relevant Business Cases:**
>
> - **Business Case 2: Secure Data Management for Sensitive and Heterogeneous Datasets**.
>
> - **Business Case 5: Open Dissemination of Research Outputs**.
>
> **Actors:**
>
> Curator; Privacy Office or Research Ethics Board; INN Digital Ecosystem.
>
> **Preconditions:**
>
> Identifiable source data is held on a governed machine, with its consent terms and agreements attached.
>
> **Trigger:**
>
> A curator starts preparing a dataset for analysis or release.
>
> **Main Flow:**
>
> 1.  The source data is converted to BIDS on the governed machine.
>
> 2.  The dataset is validated against the BIDS specification.
>
> 3.  The data is de-identified (for example, faces removed from scans) as an authorized, recorded step.
>
> 4.  The privacy office or ethics board reviews the result where the consent terms or agreements require it.
>
> 5.  The prepared dataset is released as a new dataset, linked to its source by provenance, with the conditions that still apply to it.
>
> **Postconditions:**
>
> The identifiable source stays on the governed machine. The released dataset records how it was derived and which conditions it carries.
>
> **Exceptions:**
>
> **Validation or Review Failure**: the dataset is not released; the curator is told what failed.
>
> **Functional Requirements:**
>
> - BIDS conversion and validation on the governed machine.
>
> - De-identification recorded as a step in the dataset’s provenance.
>
> - Release linked to its source, carrying the conditions that still apply.
>
> **Non-Functional Requirements:**
>
> Compliance with TCPS2 ([Canadian Institutes of Health Research, Natural Sciences and Engineering Research Council of Canada, and Social Sciences and Humanities Research Council of Canada 2022](#ref-tcps2)) (coded data remains identifiable) and provincial privacy law, under which de-identifying is itself a use of the data.

> *New since June 2025.*
>
> ## <a id="s6"></a>6 Traceability to the Open Scholarship Principles
>
> A filled mark (●) indicates a primary contribution; an open mark (○) a supporting one.
>
> |                                    |        |         |          |         |         |        |
> |:-----------------------------------|:-------|:--------|:---------|:--------|:--------|:-------|
> |                                    | **P1** | **P2**  | **P3**   | **P4**  | **P5**  | **P6** |
> |                                    | Equity | Sharing | Autonomy | Privacy | Support | IP     |
> | G1 Modular infrastructure          | ●      | ○       |          |         | ●       |        |
> | G2 Secure data management          |        | ●       | ○        | ●       |         |        |
> | G3 Computational tools             | ○      | ●       |          | ○       | ●       |        |
> | G4 External integration            | ●      | ●       |          | ○       |         |        |
> | G5 Open dissemination              |        | ●       |          | ○       | ●       | ●      |
> | G6 Sustainability                  |        |         |          |         | ●       |        |
> | W1 Secure storage and access       |        | ○       |          | ●       |         |        |
> | W2 Data sharing                    | ●      | ●       |          | ●       |         |        |
> | W3 Preparation and analysis        |        | ●       |          | ○       |         |        |
> | W4 Custom pipelines                | ○      | ●       |          |         |         | ○      |
> | W5 Retrieving results              |        | ○       |          | ●       |         |        |
> | W6 External data integration       | ●      | ○       |          | ●       |         |        |
> | W7 Consent, withdrawal, governance | ○      |         | ●        | ●       |         |        |
> | W8 Publishing and depositing       |        | ●       |          | ○       | ●       | ●      |

> **Proposal, not yet agreed.**
>
> ## <a id="s7"></a>7 Proposals for Discussion
>
> The two proposals below are not yet agreed. They are included for discussion.
>
> ### <a id="s7-1"></a>7.1 Proposal A: Infrastructure that Follows Research Relationships
>
> #### Grounding.
>
> This proposal puts INN’s value of Complex Systems Thinking into practice: people and social structures form an extended network that continuously informs how INN works and what it learns (Section [2.2](#s2-2)).
>
> #### Premise.
>
> Science is social. INN research is carried out through formal relationships — appointments, supervision, grants, data usage agreements with hospital partners — and informal ones: a colleague asked to check an analysis, a trainee who joins for a term, a clinical collaborator whose role grows. These relationships change constantly. The infrastructure encodes a model of them (who can see which data, who can run which analysis). When the model lags behind reality, friction follows in both directions:
>
> - **Missing access**: a new collaborator waits on an administrator; work stalls or moves to ungoverned channels (emailed files, personal cloud storage).
>
> - **Stale access**: people who have left a project, and collaborations that have ended, keep their access. This is a direct privacy risk (Principle 4).
>
> The proposal is to treat *correspondence* between the digital infrastructure and INN’s actual research relationships as a design goal. Routine adjustments would be made by researchers themselves, with minimal IT involvement, inside limits that governance sets and the platform enforces.
>
> #### Design commitments.
>
> - **Researcher-driven**: adding and removing collaborators and adjusting roles are done by researchers, not by administrators on their behalf.
>
> - **Bounded delegation**: those who hold access can extend it only within the limits set by agreements and governance, and those limits carry forward.
>
> - **Relationship lifecycles**: access is tied to a project, collaboration or agreement, and ends or is reviewed when the relationship does.
>
> - **Legibility**: researchers, stewards and participants can see who has access to what, and through which relationship.
>
> - **Governance sets the bounds**: consent terms, data usage agreements and steward decisions are encoded once, by those accountable, and every change is checked against them. For hospital data, project membership alone would never be sufficient.
>
> #### Relation to the INN Data Portal.
>
> The portal already contains the seeds of this approach: project managers can manage their own projects’ members and policies, and a data model for agreements (a set of policies with a lifespan) exists but is not yet implemented. Today, however, policies are held per user and are not derived from project membership, so removing someone from a project does not remove their access.
>
> #### Relation to “people over process”.
>
> SFU’s Open Scholarship team has described “people over process” as its guiding theme ([Higino and Shen 2026](#ref-higino2026eorc)). This proposal is complementary: it asks that processes be *adaptive*, reshaped by the people they serve as their relationships change. Where processes cannot adapt, “people over process” tends to become “people around process”: workarounds that are neither open nor governed.
>
> #### If adopted.
>
> It would add a goal (researcher-driven adaptation of the infrastructure) and a workflow (adjusting access as collaborations change). Time-to-access and stale access would be measured as indicators of friction.
>
> ### <a id="s7-2"></a>7.2 Proposal B: Confidential Computing for Highly Sensitive Data
>
> #### Current state.
>
> Most INN computation runs in the federated environment. Private compute is reserved for highly sensitive data, where capacity, particularly GPU capacity for neuro-AI, is limited and costly.
>
> #### Proposal.
>
> Reduce dependence on private compute by keeping data encrypted except at the point of computation:
>
> - **Confidential computing** (hardware-isolated execution, e.g., AMD SEV-SNP ([Advanced Micro Devices 2020](#ref-amd2020snp)), Intel TDX, and GPUs with confidential-computing modes ([Apsey et al. 2023](#ref-nvidia2023h100))). Data is decrypted only inside an isolated, attested environment that system operators cannot inspect. Overhead is modest compared with the alternatives below ([Misono et al. 2024](#ref-misono2024cvm)).
>
> - **Attestation-gated key release.** The decryption key is released only to a workload that proves, through remote attestation, that it is running approved code on approved hardware. The decision to release the key would come from the same agreements that already govern storage access (contracts instantiated as policies), extending them from storage into compute.
>
> - **Federated learning** ([McMahan et al. 2017](#ref-mcmahan2017); [Rieke et al. 2020](#ref-rieke2020)) for hospital partners: the model travels to the data, and the data stays on site.
>
> - **Fully homomorphic encryption** ([Gentry 2009](#ref-gentry2009)) (computing directly on encrypted data) only for narrow workloads such as simple statistics. It is orders of magnitude too slow for training imaging models.
>
> #### Caveats.
>
> - **Outputs are not protected by encryption.** A model trained in an enclave can still memorize and leak patient data ([Shokri et al. 2017](#ref-shokri2017); [Carlini et al. 2023](#ref-carlini2023)). Release review (use case 5.6) is still required.
>
> - **Agreements may constrain location, not only exposure.** Where a data usage agreement requires data to remain on premises or in Canada, encryption alone does not satisfy it.
>
> - **Hardware availability is unconfirmed.** Whether Alliance or SFU systems enable confidential-computing modes has not been established, and that is the first thing to check.

> *New since June 2025.*
>
> ## <a id="s8"></a>8 Open Questions
>
> - **Archiving scope.** Long-term archiving stays out of scope, but published outputs need persistent records. The division of responsibility with SFU Library and external repositories needs to be agreed.
>
> - **Openness versus privacy.** Principles 2 and 4 pull in different directions for much INN data. Tiering and stated reasons for restriction manage the tension but do not remove it.
>
> - **Models as outputs.** Release criteria for models trained on restricted data need to be defined with data holders and the Office of Research Ethics.
>
> - **Openness as default, not obligation.** Researchers and partners may decline open-science activities. Adoption metrics must not become de facto mandates.
>
> - **International collaboration.** Data localization and cross-border transfer rules increasingly constrain neuroscience collaboration. INN’s approach (governance in place, analysis brought to data) suits this, but jurisdiction-specific requirements have not yet been mapped for INN’s international partners.
>
> - **Alignment with the Open Scholarship implementation plan.** The Open Scholarship Framework’s 3-year implementation plan was drafted in 2025 and is refined and prioritized by its steering committee; its announced rollout is resources and training for researchers ([Simon Fraser University, n.d.b](#ref-sfuosframework)). It has not yet been published. Most of the tooling in this strategy is required by INN’s own goals; if the plan specifies additional infrastructure, this strategy should be reviewed against it.
>
> - **Alignment with community efforts.** International efforts such as the Brain Research International Data Governance Exchange (BRIDGE) are developing machine-readable governance labels, consent frameworks and model registries for neural data ([Ray et al. 2026](#ref-ray2026)). INN’s implementation should align with them rather than diverge.

## <a id="s9"></a>9 Changes from the June 2025 Strategy

Changes relative to the INN Digital Infrastructure Strategy of 19 June 2025 ([Institute for Neuroscience and Neurotechnology and Research Computing Group 2025](#ref-inn2025strategy)).

## References



<a id="ref-amd2020snp"></a>Advanced Micro Devices. 2020. “<span class="nocase">AMD SEV-SNP: Strengthening VM Isolation with Integrity Protection and More</span>.” White paper 70366. <https://www.amd.com/content/dam/amd/en/documents/epyc-business-docs/white-papers/SEV-SNP-strengthening-vm-isolation-with-integrity-protection-and-more.pdf>.

<a id="ref-nvidia2023h100"></a>Apsey, Emily, Phil Rogers, Michael O’Connor, and Rob Nertney. 2023. “<span class="nocase">Confidential Computing on NVIDIA H100 GPUs for Secure and Trustworthy AI</span>.” NVIDIA Technical Blog, 3 August 2023. <https://developer.nvidia.com/blog/confidential-computing-on-h100-gpus-for-secure-and-trustworthy-ai/>.

<a id="ref-bischoffgrethe2007"></a>Bischoff-Grethe, Amanda, I. Burak Ozyurt, Evelina Busa, Brian T. Quinn, Christine Fennema-Notestine, Camellia P. Clark, Shaunna Morris, et al. 2007. “A Technique for the Deidentification of Structural Brain MR Images.” *Human Brain Mapping* 28 (9): 892–903. <https://doi.org/10.1002/hbm.20312>.

<a id="ref-borealis"></a>Borealis. n.d. “Borealis: The Canadian Dataverse Repository.” <https://borealisdata.ca>.

<a id="ref-triagency2021rdm"></a>Canadian Institutes of Health Research, Natural Sciences and Engineering Research Council of Canada, and Social Sciences and Humanities Research Council of Canada. 2021. “Tri-Agency Research Data Management Policy.” <https://science.gc.ca/site/science/en/interagency-research-funding/policies-and-guidelines/research-data-management/tri-agency-research-data-management-policy>.

<a id="ref-tcps2"></a>———. 2022. “<span class="nocase">Tri-Council Policy Statement: Ethical Conduct for Research Involving Humans – TCPS 2 (2022)</span>.” <https://ethics.gc.ca/eng/policy-politique_tcps2-eptc2_2022.html>.

<a id="ref-carlini2023"></a>Carlini, Nicholas, Jamie Hayes, Milad Nasr, Matthew Jagielski, Vikash Sehwag, Florian Tramèr, Borja Balle, Daphne Ippolito, and Eric Wallace. 2023. “Extracting Training Data from Diffusion Models.” In *32nd USENIX Security Symposium*. <https://www.usenix.org/conference/usenixsecurity23/presentation/carlini>.

<a id="ref-carroll2020care"></a>Carroll, Stephanie Russo, Ibrahim Garba, Oscar L. Figueroa-Rodríguez, Jarita Holbrook, Raymond Lovett, Simeon Materechera, Mark Parsons, et al. 2020. “The CARE Principles for Indigenous Data Governance.” *Data Science Journal* 19: 43. <https://doi.org/10.5334/dsj-2020-043>.

<a id="ref-dandi"></a>DANDI Archive. n.d. “<span class="nocase">DANDI: Distributed Archives for Neurophysiology Data Integration</span>.” <https://dandiarchive.org>.

<a id="ref-nifti"></a>Data Format Working Group. n.d. “<span class="nocase">NIfTI: Neuroimaging Informatics Technology Initiative data format</span>.” <https://nifti.nimh.nih.gov>.

<a id="ref-alliance"></a>Digital Research Alliance of Canada. n.d. “<span class="nocase">Digital Research Alliance of Canada</span>.” <https://alliancecan.ca>.

<a id="ref-dwork2014"></a>Dwork, Cynthia, and Aaron Roth. 2014. “The Algorithmic Foundations of Differential Privacy.” *Foundations and Trends in Theoretical Computer Science* 9 (3–4): 211–407. <https://doi.org/10.1561/0400000042>.

<a id="ref-ec2016fair"></a>European Commission, Directorate-General for Research & Innovation. 2016. “<span class="nocase">H2020 Programme: Guidelines on FAIR Data Management in Horizon 2020, Version 3.0</span>.”

<a id="ref-gdpr"></a>European Parliament and Council of the European Union. 2016. “Regulation (EU) 2016/679 (General Data Protection Regulation).” Official Journal of the European Union, L 119.

<a id="ref-ocap"></a>First Nations Information Governance Centre. n.d. “<span class="nocase">The First Nations Principles of OCAP<sup></sup></span>.” <https://fnigc.ca/ocap-training/>.

<a id="ref-gentry2009"></a>Gentry, Craig. 2009. “Fully Homomorphic Encryption Using Ideal Lattices.” In *Proceedings of the 41st Annual ACM Symposium on Theory of Computing (STOC)*, 169–78. <https://doi.org/10.1145/1536414.1536440>.

<a id="ref-gorgolewski2016bids"></a>Gorgolewski, Krzysztof J., Tibor Auer, Vince D. Calhoun, R. Cameron Craddock, Samir Das, Eugene P. Duff, et al. 2016. “The Brain Imaging Data Structure, a Format for Organizing and Describing Outputs of Neuroimaging Experiments.” *Scientific Data* 3: 160044. <https://doi.org/10.1038/sdata.2016.44>.

<a id="ref-higino2026eorc"></a>Higino, Gracielle, and Kelly Shen. 2026. “<span class="nocase">Open scholarship strategic planning at Simon Fraser University, Canada</span>.” Edinburgh Open Research Conference, abstract and slides. <https://zenodo.org/records/22781227>.

<a id="ref-innopenscience"></a>Institute for Neuroscience and Neurotechnology. n.d.a. “Open Science.” Simon Fraser University. <https://www.sfu.ca/neuro-institute/open-science.html>.

<a id="ref-innbuyin"></a>———. n.d.b. “Open Science Buy-In Project.” Simon Fraser University; completed June 2024. <https://www.sfu.ca/neuro-institute/open-science/open-science-buyin.html>.

<a id="ref-innvalues"></a>———. n.d.c. “<span class="nocase">Vision, Mission and Values</span>.” Simon Fraser University. <https://www.sfu.ca/neuro-institute/about.html>.

<a id="ref-inn2025strategy"></a>Institute for Neuroscience and Neurotechnology, and Research Computing Group. 2025. “INN Digital Infrastructure Strategy.” Simon Fraser University, internal document, 19 June 2025.

<a id="ref-kaye2015"></a>Kaye, Jane, Edgar A. Whitley, David Lund, Michael Morrison, Harriet Teare, and Karen Melham. 2015. “Dynamic Consent: A Patient Interface for Twenty-First Century Research Networks.” *European Journal of Human Genetics* 23 (2): 141–46. <https://doi.org/10.1038/ejhg.2014.71>.

<a id="ref-markiewicz2021openneuro"></a>Markiewicz, Christopher J., Krzysztof J. Gorgolewski, Franklin Feingold, Ross Blair, Yaroslav O. Halchenko, Eric Miller, Nell Hardcastle, et al. 2021. “The OpenNeuro Resource for Sharing of Neuroscience Data.” *eLife* 10: e71774. <https://doi.org/10.7554/eLife.71774>.

<a id="ref-mcmahan2017"></a>McMahan, H. Brendan, Eider Moore, Daniel Ramage, Seth Hampson, and Blaise Agüera y Arcas. 2017. “Communication-Efficient Learning of Deep Networks from Decentralized Data.” In *Proceedings of the 20th International Conference on Artificial Intelligence and Statistics (AISTATS)*, 54:1273–82. PMLR.

<a id="ref-misono2024cvm"></a>Misono, Masanori, Dimitrios Stavrakakis, Nuno Santos, and Pramod Bhatotia. 2024. “Confidential VMs Explained: An Empirical Analysis of AMD SEV-SNP and Intel TDX.” *Proceedings of the ACM on Measurement and Analysis of Computing Systems* 8 (3). <https://doi.org/10.1145/3700418>.

<a id="ref-dicom"></a>National Electrical Manufacturers Association. n.d. “<span class="nocase">Digital Imaging and Communications in Medicine (DICOM) Standard, PS3</span>.” <https://www.dicomstandard.org>.

<a id="ref-sfustarterkit2026"></a>Open Scholarship at SFU. 2026. “<span class="nocase">Open Scholarship Starter Kit, first edition</span>.” Zenodo. <https://zenodo.org/records/18778502>.

<a id="ref-poupon2017tosi"></a>Poupon, Viviane, Annabel Seyller, and Guy A. Rouleau. 2017. “The Tanenbaum Open Science Institute: Leading a Paradigm Shift at the Montreal Neurological Institute.” *Neuron* 95 (5): 1002–6. <https://doi.org/10.1016/j.neuron.2017.07.026>.

<a id="ref-fippa"></a>Province of British Columbia. n.d. “<span class="nocase">Freedom of Information and Protection of Privacy Act</span>.” RSBC 1996, c. 165.

<a id="ref-ray2026"></a>Ray, Kimberly L., Marietjie Botes, Melanie Collier, Alden Yi, Steven Hershman, Thaís Monteiro, Mariana Genuino, et al. 2026. “Reconciling Global Collaboration and Data Sovereignty in Neuroscience.” *Nature Neuroscience*. <https://doi.org/10.1038/s41593-026-02468-w>.

<a id="ref-rieke2020"></a>Rieke, Nicola, Jonny Hancox, Wenqi Li, et al. 2020. “The Future of Digital Health with Federated Learning.” *Npj Digital Medicine* 3: 119. <https://doi.org/10.1038/s41746-020-00323-1>.

<a id="ref-rubel2022nwb"></a>Rübel, Oliver, Andrew Tritt, Ryan Ly, Benjamin K. Dichter, Satrajit Ghosh, Lawrence Niu, Pamela Baker, et al. 2022. “The Neurodata Without Borders Ecosystem for Neurophysiological Data Science.” *eLife* 11: e78362. <https://doi.org/10.7554/eLife.78362>.

<a id="ref-schwarz2019"></a>Schwarz, Christopher G., Walter K. Kremers, Terry M. Therneau, Richard R. Sharp, Jeffrey L. Gunter, Prashanthi Vemuri, Arvin Arani, et al. 2019. “Identification of Anonymous MRI Research Participants with Face-Recognition Software.” *New England Journal of Medicine* 381 (17): 1684–86. <https://doi.org/10.1056/NEJMc1908881>.

<a id="ref-summit"></a>SFU Library. n.d. “<span class="nocase">Summit: SFU’s Institutional Repository</span>.” <https://summit.sfu.ca>.

<a id="ref-sfunews2025"></a>SFU News. 2025. “<span class="nocase">SFU first in Canada to adopt university-wide open scholarship framework</span>.” Simon Fraser University, 27 March 2025. <https://www.sfu.ca/sfunews/stories/2025/03/sfu-first-in-canada-to-adopt-university-wide-open-scholarship-fr.html>.

<a id="ref-shokri2017"></a>Shokri, Reza, Marco Stronati, Congzheng Song, and Vitaly Shmatikov. 2017. “Membership Inference Attacks Against Machine Learning Models.” In *2017 IEEE Symposium on Security and Privacy*, 3–18. <https://doi.org/10.1109/SP.2017.41>.

<a id="ref-sfuos"></a>Simon Fraser University. 2025. “<span class="nocase">SFU Open Science and Open Scholarship Principles</span>.” <https://www.sfu.ca/content/dam/sfu/neuro-institute/Files/open-science-project/OS-Principles_approved.pdf>.

<a id="ref-sfurdm"></a>———. n.d.a. “Institutional Research Data Management Strategy.” Office of the Vice-President, Research and International. <https://www.sfu.ca/research/researcher-resources/plan-my-research/compliance/research-data-management.html>.

<a id="ref-sfuosframework"></a>———. n.d.b. “Open Scholarship Framework.” <https://www.sfu.ca/research/research-impact/performance-excellence/open-science.html>.

<a id="ref-tosi"></a>The Neuro, McGill University. n.d. “Tanenbaum Open Science Institute (TOSI).” <https://www.mcgill.ca/neuro/open-science/tanenbaum-open-science-institute-tosi>.

<a id="ref-hipaa"></a>United States Congress. 1996. “<span class="nocase">Health Insurance Portability and Accountability Act of 1996</span>.” Public Law 104–191.

<a id="ref-wilkinson2016fair"></a>Wilkinson, Mark D., Michel Dumontier, IJsbrand Jan Aalbersberg, Gabrielle Appleton, Myles Axton, Arie Baak, et al. 2016. “The FAIR Guiding Principles for Scientific Data Management and Stewardship.” *Scientific Data* 3: 160018. <https://doi.org/10.1038/sdata.2016.18>.
