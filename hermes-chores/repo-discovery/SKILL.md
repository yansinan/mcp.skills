---
name: repo-discovery
description: "Class-level skill: discovering topic-specific projects within a GitHub account."
version: 0.1.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [GitHub, discovery, search, repositories]
    related_skills: [github-repo-management, github-auth]
---

# Repo Discovery

This skill standardizes how agents discover whether a GitHub user/org has a project for a specific topic (e.g., "primary school mathematics"). It bundles checklist, queries, interpretation heuristics, and templates to present candidates to the user for confirmation.

## Triggers
- User asks "Do I have a project X?" or "Find my project about Y"
- When repository names are ambiguous or missing and the agent must surface candidate repos

## Steps
1. Normalize the query: generate spelling variants, language translations (Chinese/English), and common subject keywords.
2. Run exact repo-name search (user:USERNAME + title variants). If matches, return immediately with README/description snippet.
3. If no exact name match, search README/docs across repos (higher signal of project purpose).
4. If still no match, run code search for topical keywords across user's repos (broad recall).
5. Rank candidates by: README hit > docs > top-level file > code file; then by stars and recent activity.
6. Present top N candidates (N=5) with metadata and matching snippets; ask user to confirm which is "primary".

## Output format
- Table: repo | description | language | stars | last_updated | matching_path | snippet

## Support files
- references/search-queries.md  (cheat-sheet of queries and keywords)
- templates/result-table.md    (presentation template)

