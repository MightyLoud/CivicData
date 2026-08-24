# Bounded External Acceptance Protocol

## Objective

Determine whether another civic-data team can independently consume Seattle and Tacoma without access to the source spreadsheets or private builder conversations.

## Required tasks

For each tested jurisdiction:

1. Resolve the jurisdiction by canonical ID.
2. Resolve it by OCD jurisdiction ID.
3. Resolve it by Census Government Units PID.
4. Return all modeled Offices and identify which are public-elected.
5. Return exactly one current RoleTerm per modeled Office.
6. Open evidence for at least three record classes.
7. Identify every published known gap.
8. Explain one temporal transition without builder clarification.

Additional Tacoma tasks:

9. Explain why Tacoma has 16 modeled Offices but 15 public-elected Offices.
10. Reconstruct Department 2 as retirement → vacancy → appointment → election.

## Pass standard

The release receives external PASS when the partner confirms that no source spreadsheet, undocumented assumption, Tacoma-specific serialization, or breaking schema change was required.

A failure should identify the exact field, relationship, wording, or artifact that blocked independent use. Do not give a courtesy PASS.
