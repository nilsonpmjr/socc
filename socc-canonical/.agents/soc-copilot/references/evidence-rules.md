# Evidence Rules

Use these rules across all SOC Copilot skills:

## Facts vs inference

- A fact is directly present in the artifact, log, or enrichment data.
- An inference is a conclusion drawn from one or more facts.
- Mark strong inferences with clear reasoning.
- Avoid weak inferences when they do not change analyst action.

## Confidence guidance

- `0.0 - 0.3`: weak signal, missing context, or ambiguous artifact
- `0.4 - 0.6`: multiple suspicious indicators but incomplete proof
- `0.7 - 0.85`: strong suspicious or malicious pattern with concrete indicators
- `0.86 - 1.0`: only when evidence is strong, specific, and internally consistent

## Verdict guidance

- `benigno`: evidence supports a harmless explanation
- `suspeito`: risky patterns exist but proof is incomplete
- `malicioso`: strong evidence of abuse or malicious intent
- `inconclusivo`: insufficient, partial, or contradictory evidence

## Recommendation style

- Prefer actions the analyst can take now
- Put safest validation steps before disruptive containment steps
- Avoid irreversible actions unless risk is strong and clearly explained
