**TERMS OF USE**

These Terms of Use (the “Terms”) define the general conditions for the usage of the source code package called the SEO Skills Package (the “Package”) available on https://github.com/Senuto/nodeshub-seo-skills. These Terms have been prepared in accordance with applicable legal regulations, in particular:

- The Civil Code – Act of 23 April 1964 (Journal of Laws of 1964, No. 16, item 93, as amended) (hereinafter referred to as the “Civil Code”),  
- The Act of 4 February 1994 on Copyright and Related Rights (consolidated text Journal of Laws of 2006 No. 90, item 631, as amended) (hereinafter referred to as the “Copyright Act”).

1. 

This Package has been provided by SENUTO SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ, headquartered in Warsaw (02-738), ul. Dominikańska 13, registered in the National Court Register by the District Court for the Capital City of Warsaw, 13th Commercial Division, KRS no. 0000464809, NIP: 9512367837, REGON: 146703642, with a share capital of PLN 9,678,200.00 (the “Provider”). The Provider owns and operates the Nodeshub tool available under below website address:  [https://nodeshub.io/](https://nodeshub.io/) (the “Nodeshub”) and provides the users with services of Nodeshub. 

The Provider is making this Package available for demonstration and promotional purposes of Nodeshub. The Package showcases the capabilities of automating SEO tasks using the Nodeshub and is intended to familiarise potential users with the Nodeshub's functionality.

The Package and Nodeshub are intended exclusively for entities that are not consumers. By Consumer this Terms define a natural person entering into a service agreement for Nodeshub with the Provider or a natural person using the Package not directly related to their business or professional activity. Provisions for consumers also apply to natural persons entering into agreements directly related to their business, provided the nature of the agreement indicates it is not of a professional character, particularly in relation to their registered business activity in CEIDG. This means that only non-consumer entities may use the Package. By accepting these Terms, you declare and confirm that you are acting in connection with your business or professional activity. If the Provider becomes aware that the you are a consumer—despite the aforementioned restrictions and declaration—it has the right to block your use of the Package, prevent you from downloading updates for it, and block your access to Nodeshub, if you have such an access either as a trail account or with purchased credits, with immediate effect. This does not exclude other claims the Provider may have, especially those arising from false declarations made by you downloading or attempting to download the Package.

Furthermore, the Provider expressly states that the downloading of resources by non-professional users does not imply that such users are granted the right to purchase or use the Nodeshub application in any way, and the Provider of the Nodeshub application is under no obligation whatsoever to allow non-professional users to use the Nodeshub application;

2. 

This Package consist of the following items:

A. SEO Automation Scripts – 10 modules  
Each module is a separate directory containing an instruction file (SKILL.md), Python scripts, and tests. All require a Nodeshub API key.

| \# | Module | Skill name | Function | Cost per use |
| :---- | :---- | :---- | :---- | :---- |
| A1 | Keyword Research | nod-keyword-research | Discovers keywords related to a topic. Iteratively scans Google results (People Also Ask and Related Searches) and generates variants via the Nodeshub API. Output: CSV list with hundreds of keywords grouped by discovery source. | 7.5–30 tokens |
| A2 | SERP Analysis | nod-serp-analysis | Analyzes Google page 1 for a given keyword: who ranks in positions 1–10, which special elements Google displays (AI Overview, Knowledge Panel, Video, Local Pack), and the dominant search intent type. | 1 token |
| A3 | SERP Clusters | nod-serp-clusters | Groups a keyword list by Google results similarity – keywords that trigger the same ranking pages land in one cluster. Uses the Louvain algorithm and optional LLM (OpenRouter) for cluster naming. Generates an interactive HTML dendrogram (D3.js visualization). | 1 token/keyword \+ LLM cost |
| A4 | Content Brief | nod-content-brief | Generates a brief for copywriters: combines SERP analysis (what ranks, what headings, what structure) with keyword expansion and an optional competitor content crawl (Jina Reader). Output: a ready-to-write brief with suggested article structure, headings, and target keywords. | \~8.5 tokens |
| A5 | Content Auditor | nod-content-auditor | Audits the user's existing content against current Google results: compares it with the top 10, and identifies missing topics, keywords, and structural elements. | \~8.5 tokens \+ Jina Reader |
| A6 | Rank Tracker | nod-rank-tracker | Checks and saves the user's domain position in Google for a selected keyword list. Creates daily JSON snapshots and compares changes over time. | 1 token/keyword |
| A7 | Competitor Tracker | nod-competitor-tracker | Monitors competitors' domain positions in Google for the same keywords as the user. Shows who ranks where and how positions change. | 1 token/keyword |
| A8 | Visibility Monitor | nod-visibility-monitor | Calculates a domain's SEO visibility score – a weighted sum of Google positions for a given keyword list. Enables competitor comparison and trend tracking. | 1 token/keyword |
| A9 | Featured Snippet Hunter | nod-featured-snippet-hunter | Finds 'position zero' opportunities in Google (Featured Snippet / Answer Box). For a domain and keyword list, identifies: where the user can capture a snippet from a competitor, where they need to defend their own, and where new opportunities exist. | 1 token/keyword |
| A10 | PAA Miner | nod-paa-miner | Extracts questions from Google's 'People Also Ask' section for a keyword list. Includes deduplication and optional thematic grouping via LLM. Output: a question bank for FAQ pages and content creation. | 1 token/keyword \+ optional LLM |

B. AI Content Detection – 1 module

| \# | Module | Skill name | Function | Cost |
| :---- | :---- | :---- | :---- | :---- |
| B1 | AI Score | ai-score | Analyzes text for the probability of AI generation. Returns: a score from 0–100%, writing style classification, and optional humanization guidelines. Supports text, files, and URLs (via Jina Reader). | Genuino API credits |

C. Connection Wizards – 5 modules

Text-based setup instructions with no executable code. Free.

| \# | Module | Skill name | Function |
| :---- | :---- | :---- | :---- |
| C1 | Connect Nodeshub | connect-nodeshub | Walks through registration at nodeshub.io, API key retrieval, and saving credentials to the project configuration. |
| C2 | Connect OpenRouter | connect-openrouter | Walks through OpenRouter API key retrieval (used for LLM-powered cluster naming). |
| C3 | Connect Genuino | connect-genuino | Walks through Genuino API key retrieval (for AI content detection). |
| C4 | Connect GSC | connect-gsc | Walks through OAuth setup for Google Search Console (click and impression data from Google). |
| C5 | Connect GA4 | connect-ga4 | Walks through OAuth setup for Google Analytics 4 (website traffic data). |

D. Agents – Multi-step Pipelines – 3 modules

Orchestrators that combine multiple modules into automated workflows. Require API keys for all constituent modules.

| \# | Module | Agent name | Function | Uses modules |
| :---- | :---- | :---- | :---- | :---- |
| D1 | Topic Planner | topic-planner | Full topic research: keyword → expansion → clustering → competitor crawl → content briefs. Saves results at each step and can be resumed from any point. | A1 \+ A3 \+ A4 |
| D2 | Keyword to Publish | keyword-to-publish | End-to-end keyword-to-article pipeline: research → SERP analysis → brief → Claude writes the article → AI score check → corrections → audit against competitors. | A1 \+ A2 \+ A4 \+ A5 \+ B1 |
| D3 | Content Humanizer | content-humanizer | Iterative text humanization: checks AI score → rewrites flagged sections → rechecks → repeats until the score drops below the threshold. Maximum 3 iterations. | B1 |

E. HTML Report Generator – 1 module

A Python script (\~350 lines) that generates self-contained HTML files with analysis results. Includes: summary cards, data tables, bar charts, a table of contents, and a responsive layout. Uses the branding configuration defined in section G. No API key required.

F. Product Context Templates – 6 files

Empty Markdown files for the user to fill with their product data: product description, target audiences, voice and tone, competitor analysis, proof points, and brand guidelines. These files serve as context for content generation.

G. Branding Configuration – 4 files

A JSON config file (colors, fonts, company data, and report settings), two SVG logos (for light and dark backgrounds; default: Nodeshub), and a helper script for extracting styles from a website.

H. Installer – 1 file

A Node.js script that copies all of the elements listed above into the user's project directory.

I. Documentation – 5 files

Main documentation (README.md – what it is, installation, module list, API costs), Claude Code instructions (CLAUDE.md – working rules, module registry, conventions), agent specification (AGENTS.md – architecture and dependencies), contribution guide (CONTRIBUTING.md – how to create custom extensions), and a module validation script (validate-skills.sh).

The aforementioned components of the Package are provided solely for the purpose of demonstrating the basic functions of the Nodeshub application and do not provide a complete picture of Nodeshub. You may use the Package locally on your computer or your own server using Claude Code. However, the Provider reserves that, in order to make full use of the resources provided, it is necessary to purchase a plan on the Nodeshub website \- without such a purchase, the available resources cannot be fully utilised, due to a lack of access to the API and network data. By downloading the Package you declare that you are aware of and you accept the fact that the Package is not a completely standalone product, and to make full use of it, you may need to pay for a Nodeshub plan. Before the purchase of the Nodeshub plan you will be asked to accept the Nodeshub’s Terms of Services and Privacy Policy. 

To get started, you'll need a computer with a stable internet connection of at least 10 Mbps, a minimum of 8 GB of RAM – though 16 GB makes for a much smoother experience when running a code editor, terminal, and AI tooling side by side. A web browser alone won't be enough; the Package is designed to run as desktop software.

For the full experience – including slash commands and integrated workflows — you'll need a compatible AI coding environment such as Claude Code. Python 3.9 or newer is required to run the automation layer, and Node.js 18 or newer is needed for a handful of specific features, namely the Google Search Console and GA4 data scripts.

Most data features require your own NodesHub API key and an active internet connection. A few optional features also depend on separate accounts or keys – OpenRouter, Genuino, Jina, and Google OAuth for Search Console and GA4. Those are third-party services with their own pricing and terms, and they're not bundled with the Package.

Meeting these requirements doesn't guarantee any specific SEO outcome or uninterrupted access to third-party APIs.

3. 

The content of the Package is legally protected. The use of the Package is only permitted in accordance with these Terms. Prior to downloading and using the Package, you must read and accept these Terms. By downloading the Package you agree to these Terms and declare:  
\-  to only use it with respect to the provisions of these Terms;  
\- use the Package only within the scope authorized by the Terms;  
\- refrain from any actions that could hinder or disrupt the operation of the Nodeshub, Package or interfere with other potential users access;  
\-  refrain from interfering with or attempting to interfere with the Package or Nodeshub;  
\- use the Package appropriately and proportionally to actual needs, in accordance with its purpose.

By downloading the Package, you are granted a non-exclusive licence, free of charge and without any time or geographical restrictions, to use the Package in accordance with the terms and to the extent set out in these Terms and defined as the permitted use. 

The fact that the licence is free of charge does not mean that you do not need to purchase a Nodeshub plan in order to be able to make full use of the Package.

The fact that the licence is granted without any time limitations does not mean that your ability to use the Package or download updates to it cannot be blocked by the Provider in the event of any breach by you of the rules governing the use of the Package, as set out in these Terms. By downloading the Package you agree to these Terms and acknowledge that it can only be used in line with these Terms and any breach of the terms of use of the Package may result in you being denied the right and ability to continue using the Package and its updates.

The granting of this licence does not mean that you acquire ownership of the copies or media on which the Package is recorded, nor does it grant you the exclusive right to authorise the exercise of derivative copyright in the Package.

Permitted use of the Package is defined as follows:   
\- to download and install the Package on your own computer;  
\- to use the Package for your own business purposes (SEO analysis, content creation, ranking monitoring);  
\- to modify scripts and instructions to suit your own needs (e.g. adjusting parameters, adding your own modules) to the extent that such modification does not conflict with other provisions of these Terms;  
\- to share it further (including publicly) whilst retaining the information that all the copyrights and other intellectual property rights belong to the Provider;  
\- to create your own extensions (modules) based on the provided infrastructure;  
\- use the report generator with your own branding (logo, colours, fonts).

It is strictly prohibited to use the Package for the following purposes and in the following manner:  
\- to remove information regarding Provider’s authorship, copyrights and other intellectual property rights;  
\- to use Provider’s or Nodeshub trademarks in a way that may suggest an official affiliation or endorsement;  
\- to present the Package or any components that the Package consists of as your own original product;  
\- to resell the Package or any components that the Package consists of as a standalone commercial product;  
\- to use the Package or any components that the Package consists of to build a product that competes with Nodeshub or any other tool, application or service provided by the Provider.

For the avoidance of any doubt, it is expressly stated that all copyrights and other intellectual property rights in the Package remain with the Provider. This includes in particular the rights to text, graphics, multimedia, algorithm, scripts, concept, software, and databases. If you breach any provision of these Terms, in particular the rules governing the use of the Package set out in this clause, including any infringement of copyright or any other intellectual property rights held by the Provider in relation to the Package, the Provider has the right to block your use of the Package, prevent you from downloading updates for it, and block your access to Nodeshub, if you have such an access either as a trail account or with purchased credits, with immediate effect. Furthermore, the Provider reserves the right to seek compensation for damages and to bring other legal claims in the event that its rights are infringed by persons using the sources.

4. 

Using the Package and Nodeshub involves internet use, which carries inherent risks. These include the potential for harmful software—such as viruses, worms, and trojans—to be introduced to your device. It is strongly recommended that you maintain up-to-date antivirus and firewall protection software. There is also the risk of third parties attempting unauthorized access to your data or devices. You should keep all credentials strictly confidential to avoid such risks.

The Package, its components or Nodeshub may be temporarily unavailable due to technical activities (e.g., updates, maintenance, inspections). Downtime may also result from issues with third-party providers (e.g., hosting services). Such unavailability does not constitute grounds for any claims against the Provider. The Provider is not liable for failure to perform due to circumstances beyond its control or for technical limitations on your side (e.g., hardware, internet issues).

By accepting these Terms you acknowledge that the Package and the Nodeshube depend on external platforms, which may change their operations without notice. Such changes may affect the functioning of the Package or Nodeshub and do not justify any claims.

5. 

The Package and all of its components are provided “as-is” without any guarantees. The Provider does not guarantee that:  
\- the Package or any of its components will meet your expectations;  
\- the access to the Package or any of its components will be uninterrupted, timely, secure, or error-free;  
\- all data received through the Package or any of its components or the Nodeshub will be accurate or reliable;  
\- errors in the Package or any of its components will be fixed;  
\- content created using the Package or any of its components will be suitable for its intended audience or legally compliant.

The Provider is not obligated to update the Package, any of its components nor Nodeshub in any way. The Package and its components are current as of the time of their release. In the event of any changes to the Nodeshub, the Provider is under no obligation to modify the Package and its components so that they remain supported and functionally compatible with the Nodeshub. 

No implied warranties apply unless explicitly stated in these Terms.

To the maximum extent permitted by law, the Provider disclaims liability for any damages — direct or indirect, including pure financial losses, consequential damages (including, for example, loss of profits, revenues, business interruption, loss of data or computer programs, loss of reputation or good name, attorneys’ fees or court costs), including, in particular, damages arising directly or indirectly from:  
\- use of the Package or any of its components,  
\- reliance on any included materials,  
\- changes to the the Package or any of its components or interruptions,  
\- deletion or inaccessibility of data,  
\- technical issues or failures.

This applies regardless of the legal basis for the claim (contract, tort, statute, etc.), even if the Provider was warned of possible damages. These limitations apply to the fullest extent permitted by law.

The Provider shall not be liable for any use of the Package, any of its components nor the Nodeshub by those who download them, nor for any damage caused by them as a result of the use of Package, any of its components nor the Nodeshub, their modification, adaptation, etc. In particular, the Provider shall not be liable for any use of the Package, any of its components nor Nodeshub by anyone in a manner that breaches the terms of use of internet search engines, in particular Google Search.

6. 

As the Package is a strictly promotional material, no complaints may be made regarding its content.

The Provider and the Nodeshub reserve the right to remove, change, update the Package or any of its components at any time, as well as to block the ability to connect them to the Nodeshub and to use the Nodeshub with the Package at any time.

These Terms are governed by the laws of the Republic of Poland. Any matters not addressed in these Terms are subject to Polish law. These provisions apply only to the extent that choosing Polish law is legally permissible and do not exclude mandatory laws of other countries unless it is legally permissible to do so.

Any disputes relating to these Terms or arising from the use of the Package shall be subject to the jurisdiction of Polish courts. Specifically, disputes will be resolved by the court competent for the Provider’s registered office. These jurisdiction provisions apply only to the extent legally valid and do not override mandatory legal rules on jurisdiction.

These Terms are available in electronic form at: https://github.com/Senuto/nodeshub-seo-skills. You may download and save them for personal records.  
