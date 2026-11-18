# Task 5 conversation, round 3: reply from gpt-6.1-sol (proposal H4)

Tokens: 63359 input, 929 output.

## Its evaluation of the results

H3 does not demonstrate an improvement worth deploying. I recommend stopping this prompt-edit sequence and keeping the ORIGINAL system message as the fallback—not because it is fully compliant, but because the revisions have not established a reliable accuracy-and-safety advantage.

What worked:
• Both runs preserved the tested auto-loan and specified-tier guards.
• All supplied must-refuse tests returned the exact standard refusal without numbers.
• Checking answers included the applicable balance mappings, and savings answers included both dividend rate and APY.
• Routine effective dates were omitted, avoiding the verbosity introduced by H1.

What did not work:
• Certificate minima were still omitted in both runs, despite H3 explicitly requiring the minimum to earn. The omitted jumbo offering follows the retained standard-offering default; adding it would change scope rather than merely supply a qualifier.
• Both mortgage answers still omitted corresponding APRs despite an explicit requirement. One also converted overlapping quoted loan-amount programs into disjoint intervals, contrary to H3. The original sentence encouraging a range contributed to the initial omission, but these later results show that adding more permission or stronger wording is not reliably fixing adherence.
• Both savings answers incorrectly called the opening minimum the minimum to earn. The excerpts distinguish those fields. Full grader credit missed this factual error, so the graded result overstates answer quality.
• One card answer still included an unrequested introductory rate despite H3 expressly excluding it. This violates your scope constraint even though the supplied forbidden list did not catch it. The other run omitted that promotion, but two runs do not establish reliable control.
• Checking answers added selectively reported dividend rates without a grading benefit. They were longer than H2 without becoming more complete in a useful way.

Reference and evidence problems remain:
• The card reference rejects a standard APR range that the supplied excerpts explicitly support and the corresponding guard accepts. Its demand for business offerings conflicts with the retained personal-product default. The exact category-question excerpts also lack the personal Rewards APR numerically; generated answers must not supply it from elsewhere.
• The broad mortgage reference requires a disputed value and preferred ordering. The exact excerpts for that question were not supplied, and the related supplied excerpts support the generated disputed value. There is no justified general rule that substitutes the reference's value or ordering.
• Mortgage grading has varied across materially similar answers, including whether omitted APRs and dates cause a partial score. That variation cannot establish which edit improved correctness.

Decision: No further evidence-backed general wording change is apparent from these tests. H3 already explicitly states the requirements that the model continues to miss. Another stronger restatement would be speculative and would add instruction complexity without addressing the observed failure mode. Before further optimization, verify the actual rendered system messages used in testing, reconcile inconsistent references with the exact retrieved excerpts, and audit opening-versus-earning minima and unrequested promotions independently of the grader.

## Proposed edits (against the original system message)

## Risks it named

Keeping the ORIGINAL is a conservative fallback, not a certification of compliance: it can omit useful qualifiers and has also emitted an unrequested promotional rate. None of the tested versions guarantees the strict scope requirement.

Further enrichment increases exposure to stale-source mixing, incorrect companion pairing, and confusion among neighboring table columns. Multiple-tier tables additionally risk expanding a specified-tier question, hiding intermediate rates in a range, or inventing disjoint boundaries from overlapping examples. These problems appeared despite explicit preventive instructions.

The targeted refusal results are reassuring but do not replace a full-set test; H1 previously showed a refusal regression outside the displayed targeted runs. H2 and H3 have no supplied full-practice-set results demonstrating superiority to the original.

Do not repair reference inconsistencies by broadening offering scope, quoting promotions, or introducing unsupported values. Any future candidate should pass factual provenance and scope checks in addition to the existing keyword and reference-based grading.

Recommends stopping: True. Version it would keep: original
