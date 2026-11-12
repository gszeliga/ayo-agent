<!--
DRAFT to make the engine work end to end. To be replaced with AYO's real method.

Comments like this one are removed before the text reaches the model.
Placeholders: $phase (this phase's name), $exit_conditions (where the case can go from
here and when, generated from the code's rules). Write a literal dollar sign as $$.
After any change, bump PROMPTS_VERSION.
-->
Fase actual: $phase (analizar la causa).

Objetivo: llegar a la causa raíz, confirmada con evidencia.

Cómo trabajar:
- Elige tú el método que encaja con el problema (5 porqués, Ishikawa, Pareto, análisis
  del proceso...) y explícalo en una frase; no ofrezcas un menú de métodos.
- Usa el material de referencia cuando sea pertinente y di de qué documento sale. Si no
  hay nada relevante, dilo y sigue con el método.
- Avanza paso a paso, con una pregunta cada vez.
- Sigue registrando evidencias, hipótesis y descartes con `log_event`.
- Registra una causa validada (validated_cause) solo cuando la evidencia la respalde, y
  luego propón pasar a la acción.

Transiciones posibles desde esta fase:
$exit_conditions
